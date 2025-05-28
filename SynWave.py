# Oh, look, imports. The usual suspects. Tkinter for the pretty (?) bits,
# struct for when we need to speak in tongues (binary), math because numbers,
# threading because apparently one thing at a time is for chumps,
# time for... well, time, os for... actually, are we even using os directly? (Spoiler: No, but it feels important to have)
# pygame for the NOISE, random for when we don't know what we're doing,
# and json because saving settings in hieroglyphics was frowned upon.
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import struct
import math
import threading
import time
import os # Still here, like an appendix. Useful if it bursts, I guess.
import pygame
import random
import json

# --- Constants ---
# Ah, constants. The things we swear we'll never change, until we do.
SAMPLE_RATE = 44100 # Because 44100 is a nice, round, totally arbitrary number everyone agreed on.
BUFFER_DURATION = 0.1 # seconds. How long each little sound snippet is.
                      # Too short? Choppy. Too long? Laggy. This is my "Goldilocks" attempt.
                      # Probably spent an hour tweaking this alone for "optimal performance."

# Initialize pygame (all modules) and then mixer
# "Let's get this party started!" - Pygame, probably.
pygame.init()
try:
    # The magic incantation to make sound happen.
    # If this fails, the whole "sound generator" concept is a bit... moot.
    # The buffer size 1024? Seemed like a good idea at the time. Powers of 2, ftw.
    pygame.mixer.init(frequency=SAMPLE_RATE, size=-16, channels=2, buffer=1024)
except pygame.error as e:
    # Well, that's not good. If this happens, we're basically a fancy calculator without the sound.
    # Print it out like a town crier because Tkinter might not be ready to show its fancy popups yet.
    print(f"CRITICAL AUDIO ERROR: Could not initialize Pygame mixer: {e}\nPlease ensure you have a working audio output device. Application might not function correctly.")
    # We'll bravely (or foolishly) soldier on. Maybe Tkinter can tell the user later.
    # Or maybe it'll just sit there, silently judging.

class ToneGenerator:
    # Behold! The ToneGenerator! It generates tones! (And other noises, but "NoiseGenerator" sounded less appealing)
    def __init__(self):
        # Default settings, because starting with a deafening screech is generally bad UX.
        self.frequency = 440.0  # A4, the classic. For the discerning tinnitus sufferer.
        self.beat_frequency = 4.0 # For those binaural beat vibes.
        self.phase_shift = False # To shift, or not to shift, that is the question.
        self.playing = False    # Are we making noise? Important to keep track of.
        self.thread = None      # Ah, threads. My old nemesis. Handle with care.
        self.stop_flag = False  # The "PLEASE MAKE IT STOP" flag.
        self.volume = 0.8       # 80% power! Not quite Spinal Tap's 11, but close.
        self.waveform = "sine"  # Smooth, like butter. Or a sine wave.

        self.channel = None     # Which audio channel are we currently monopolizing?
        self.needs_settings_update = True # Flag to say "Hey, stuff changed, recalculate, genius!"

        self.current_time_offset = 0.0 # Keeps track of where we are in the eternal wave.
                                       # Resetting this was key to fixing a bug where sound drifted after a while. Good times.
        self._initialize_noise_states() # Get ready for some NOISE!
        self.SOUND_END_EVENT = pygame.USEREVENT + 1 # Pygame's little way of saying "I'm done with that sound bit, what's next?"
                                                    # Using USEREVENT + 1 because +0 is probably taken by something important. Or a gremlin.

    def _initialize_noise_states(self):
        # Resetting the magical state variables for our noise algorithms.
        # If you don't do this, the noise starts sounding... weird. And not in a good, experimental way.
        self.last_brown_sample_norm = 0.0
        self.pink_b = [0.0] * 7 # Pink noise needs seven... somethings. Don't ask, just accept the magic.
        self.current_time_offset = 0.0 # Resetting this AGAIN, just to be sure. Paranoia is a virtue in programming.

    # --- Waveform Generation ---
    # Ah, the mathematical heart of the beast. Where numbers become (almost) sound.
    # Each of these functions is a tiny, self-contained miracle of trigonometry or randomness.

    def _generate_sine_sample(self, current_freq, time_val, amplitude, phase_shifted):
        # Your basic, garden-variety sine wave. Smooth, classic, reliable.
        angle = 2.0 * math.pi * current_freq * time_val
        if phase_shifted: # "Let's flip it!" - me, adding this feature.
            angle += math.pi # A full 180, just to mess with it.
        return int(amplitude * math.sin(angle)) # And... sine!

    def _generate_square_sample(self, current_freq, time_val, amplitude, phase_shifted):
        # Square wave: edgy, harsh, like a robot's argument.
        angle = 2.0 * math.pi * current_freq * time_val
        if phase_shifted:
            angle += math.pi
        # It's either full blast on or full blast off (negative). No in-betweens.
        return int(amplitude if math.sin(angle) >= 0 else -amplitude)

    def _generate_sawtooth_sample(self, current_freq, time_val, amplitude, phase_shifted):
        # Sawtooth: Ramps up, drops hard. Like my motivation on a Monday.
        norm_phase = (current_freq * time_val) % 1.0 # The modulo 1.0 is key here. Keeps it cyclical.
                                                      # Took me a bit to realize why my sawtooth sounded like a broken record.
        if phase_shifted:
            norm_phase = (norm_phase + 0.5) % 1.0 # Shift it halfway, why not?
        return int(amplitude * ((2.0 * norm_phase) - 1.0)) # Scale and shift to -1 to 1 range.

    def _generate_triangle_sample(self, current_freq, time_val, amplitude, phase_shifted):
        # Triangle: The slightly gentler cousin of the square wave.
        norm_phase = (current_freq * time_val) % 1.0
        if phase_shifted:
            norm_phase = (norm_phase + 0.5) % 1.0
        # This logic... it makes a triangle. Trust me. I drew it on a napkin.
        if norm_phase < 0.5: val_norm = (4.0 * norm_phase) - 1.0
        else: val_norm = 3.0 - (4.0 * norm_phase)
        return int(amplitude * val_norm)

    def _generate_white_noise_sample(self, amplitude):
        # White noise: Pure, unadulterated chaos. Like static on an old CRT TV.
        # Or my brain before a healthy dose of dexamfetamines.
        return int(amplitude * random.uniform(-1.0, 1.0))

    def _generate_pink_noise_sample(self, amplitude):
        # Pink noise: White noise's more sophisticated, slightly less chaotic sibling.
        # These magic numbers? Found them on the internet. They work. Don't question the oracle.
        # This filter design is (I think) Voss-McCartney. Sounds fancy, right?
        white = random.uniform(-1.0, 1.0)
        self.pink_b[0] = 0.99886 * self.pink_b[0] + white * 0.0555179
        self.pink_b[1] = 0.99332 * self.pink_b[1] + white * 0.0750759
        self.pink_b[2] = 0.96900 * self.pink_b[2] + white * 0.1538520
        self.pink_b[3] = 0.86650 * self.pink_b[3] + white * 0.3104856
        self.pink_b[4] = 0.55000 * self.pink_b[4] + white * 0.5329522
        self.pink_b[5] = -0.7616 * self.pink_b[5] - white * 0.0168980 # This one's negative! Spooky.
        pink_val_sum = (self.pink_b[0] + self.pink_b[1] + self.pink_b[2] + self.pink_b[3] +
                        self.pink_b[4] + self.pink_b[5] + self.pink_b[6] + white * 0.5362)
        self.pink_b[6] = white * 0.115926 # One more for good luck.
        normalized_pink = pink_val_sum / 5.5 # Why 5.5? Because it sounded about right after much trial and error. Science!
        clamped_pink = max(-1.0, min(1.0, normalized_pink)) # Keep it in bounds, don't want to blow the speakers (or eardrums).
        return int(amplitude * clamped_pink)

    def _generate_brown_noise_sample(self, amplitude):
        # Brown (or Brownian, or Red) noise: Deeper, rumbling. Like distant thunder, or a dodgy stomach.
        # This is basically a random walk. Simpler than pink noise, but effective.
        white = random.uniform(-1.0, 1.0)
        self.last_brown_sample_norm += white * 0.02 # The 0.02 controls the "speed" of the brownness.
        self.last_brown_sample_norm = max(-1.0, min(1.0, self.last_brown_sample_norm)) # Clampy clamp.
        return int(amplitude * self.last_brown_sample_norm)

    def generate_audio_buffer(self):
        # This is where we cook up a batch of sound. Mmm, byte arrays.
        n_channels = 1 # Mono by default, because stereo is twice the work.
        if self.waveform == "binaural_beat":
            n_channels = 2 # Oh, alright, binaural beats need stereo. Fancy.

        num_frames = int(SAMPLE_RATE * BUFFER_DURATION) # How many little sound snapshots? This many.
        _amplitude = 32767.0 # Max amplitude for 16-bit audio. Go big or go home.
        frames_byte_array = bytearray() # Our little bucket for sound data.

        for i in range(num_frames):
            # Calculate time like a meticulous clockmaker.
            time_val = self.current_time_offset + (i / SAMPLE_RATE)
            value_left = 0
            value_right = 0 # Only used if stereo, otherwise it just sits there, feeling lonely.

            # The grand "if-elif-else" chain of sound generation.
            # Pick your poison, or rather, your waveform.
            if self.waveform == "sine":
                value_left = self._generate_sine_sample(self.frequency, time_val, _amplitude, self.phase_shift)
            elif self.waveform == "square":
                value_left = self._generate_square_sample(self.frequency, time_val, _amplitude, self.phase_shift)
            elif self.waveform == "sawtooth":
                value_left = self._generate_sawtooth_sample(self.frequency, time_val, _amplitude, self.phase_shift)
            elif self.waveform == "triangle":
                value_left = self._generate_triangle_sample(self.frequency, time_val, _amplitude, self.phase_shift)
            elif self.waveform == "white_noise":
                value_left = self._generate_white_noise_sample(_amplitude)
            elif self.waveform == "pink_noise":
                value_left = self._generate_pink_noise_sample(_amplitude)
            elif self.waveform == "brown_noise":
                value_left = self._generate_brown_noise_sample(_amplitude)
            elif self.waveform == "binaural_beat":
                # Special case! Two different frequencies for that brain-tickling effect.
                left_ear_freq = self.frequency
                right_ear_freq = self.frequency + self.beat_frequency # The "beat" magic.
                # Note: phase_shift for binaural here applies to both. Could be fancier, but KISS.
                value_left = self._generate_sine_sample(left_ear_freq, time_val, _amplitude, self.phase_shift)
                value_right = self._generate_sine_sample(right_ear_freq, time_val, _amplitude, self.phase_shift)

            # Safety first! Clamp values to prevent eardrum-shattering numbers.
            # I learned this the hard way. My ears are still ringing from "that one bug".
            value_left = max(-32768, min(32767, int(value_left)))
            if n_channels == 1:
                # struct.pack: turning numbers into the raw bytes Pygame craves.
                # '<h' means little-endian signed short. The dark arts of data representation.
                frames_byte_array.extend(struct.pack('<h', value_left))
            else:
                value_right = max(-32768, min(32767, int(value_right))) # Clamp right channel too, can't be too careful.
                frames_byte_array.extend(struct.pack('<hh', value_left, value_right)) # Two shorts for stereo.

        # Keep track of time, but don't let it run away to infinity.
        # Resetting it every hour (3600s) prevents potential float precision issues... maybe.
        # Or it just makes me feel better. This line fixed a very subtle drift I chased for days.
        self.current_time_offset += BUFFER_DURATION
        if self.current_time_offset > 3600.0 : # Arbitrary large number. An hour of continuous sound.
             self.current_time_offset -= 3600.0 # "And... back to zero (almost)!"

        try:
            # The grand finale: turn our byte soup into a Pygame Sound object.
            return pygame.mixer.Sound(buffer=bytes(frames_byte_array))
        except pygame.error as e:
            # If Pygame chokes on our beautiful bytes, we need to know.
            print(f"Error creating sound buffer: {e}")
            if root and hasattr(root, "update_status_display"): # Defensive coding: is `root` even a thing yet?
                root.update_status_display(error_message=f"Sound buffer error: {e}")
            return None # Return None, the universal sign of "oops."

    def audio_loop(self):
        # The heart of the continuous playback. This runs in a separate thread,
        # otherwise the GUI would freeze. And nobody likes a frozen GUI, I dare you to ask me how I know this.
        if not pygame.mixer.get_init():
            print("Audio loop: Pygame mixer not initialized. Abandoning ship!")
            self.playing = False # Not playing if we can't, you know, play.
            if root and hasattr(root, "update_status_display"):
                root.update_status_display(error_message="Mixer not init in loop.")
            return # Nothing more to do here. Sad.

        # Try to grab an audio channel. If they're all busy, we're out of luck.
        self.channel = pygame.mixer.find_channel(True) # True means "force find one, even if busy"
                                                       # which can be a bit rude, but we need it.
        if self.channel is None:
            print("Error: No available audio channels. Is something else hogging them all?")
            if root and hasattr(root, "update_status_display"):
                root.update_status_display(error_message="No audio channels.")
            self.playing = False
            return

        self.channel.set_volume(self.volume) # Tell the channel how loud to be.
        self.channel.set_endevent(self.SOUND_END_EVENT) # "Hey channel, tell me when you're done with a sound."

        # If settings changed or we're starting fresh, re-init noise states.
        # This was a fun bug: noise sounding weird after changing settings until this was added.
        if self.needs_settings_update or self.current_time_offset == 0.0: # current_time_offset == 0.0 implies a fresh start.
            self._initialize_noise_states()
        self.needs_settings_update = False # Okay, we're up to date. For now.

        def queue_next_sound_buffer():
            # Helper function to keep the audio stream flowing.
            # This is like a DJ lining up the next track.
            if self.stop_flag: return False # If we're stopping, don't queue anything. Makes sense.
            if self.needs_settings_update:
                # This was a subtle one: if settings changed mid-buffer, the *next* buffer
                # should reflect those changes. So, re-init noise if needed.
                # Now, _initialize_noise_states() is called *before* generating the buffer if settings changed.
                # So this flag here is more of a double-check or for other types of updates.
                # Actually, the main _initialize_noise_states() call above handles the initial state.
                # This `self.needs_settings_update = False` here is crucial.
                # Without it, it might always think it needs an update if a setting changed *during* a buffer's playback.
                # Wait, the actual re-initialization for `needs_settings_update` is now handled right before `generate_audio_buffer` if needed.
                # This flag is reset outside this specific function too. My brain hurts. Let's assume it's fine.
                # The critical part is that `generate_audio_buffer` gets fresh states if `needs_settings_update` was true.
                self._initialize_noise_states() # Make sure noise is fresh if settings changed!
                self.needs_settings_update = False


            new_buffer = self.generate_audio_buffer()
            if new_buffer:
                try:
                    self.channel.queue(new_buffer) # "Here, channel, play this next."
                    return True
                except pygame.error as e:
                    # Uh oh. Pygame didn't like that buffer. This is usually bad.
                    print(f"Error queueing sound buffer: {e}")
                    if root and hasattr(root, "update_status_display"):
                         root.update_status_display(error_message=f"Queue error: {e}")
                    self.stop() # Critical failure. Pull the plug.
                    return False
            else:
                # If buffer generation failed, that's also a game-over scenario.
                print("Stopping due to buffer generation failure.")
                self.stop() # Pulls the stop_flag, which the main loop will see.
                return False

        # "Priming the pump" - queue up the first couple of buffers to get started.
        # If this fails, we can't even start.
        if not queue_next_sound_buffer(): return # First buffer.
        if not self.stop_flag and not queue_next_sound_buffer(): return # Second buffer, to ensure smooth start.

        # The main event loop for audio. Keep running as long as we're not told to stop.
        while not self.stop_flag:
            event_handled_in_loop = False
            for event in pygame.event.get(): # Check what Pygame events have happened.
                if event.type == self.SOUND_END_EVENT:
                    # One of our sound buffers finished! Time to queue another.
                    if not self.stop_flag: # Only queue if we're still supposed to be playing.
                        # The original logic for checking channel.get_busy() here was a source of headaches.
                        # Sounds would sometimes cut out because get_busy() might be false *just* as the event arrives,
                        # but before the queue is truly empty. Relying on SOUND_END_EVENT is more robust.
                        # If this queueing fails, queue_next_sound_buffer() calls self.stop(), setting the flag.
                        if not queue_next_sound_buffer():
                            # If queueing failed, the stop_flag is now true, loop will terminate.
                            # The error itself is handled in queue_next_sound_buffer.
                            pass
                    # If stop_flag is true, we just let the event pass. The loop will end.
                event_handled_in_loop = True # We did *something* with Pygame events.

            if self.stop_flag: # Double check, in case queue_next_sound_buffer set it.
                break

            # If no Pygame events, give the CPU a tiny break.
            # Without this, this loop would spin like crazy, eating CPU for breakfast.
            # 10ms is a common choice. Small enough to be responsive, large enough to save power.
            if not event_handled_in_loop:
                 pygame.time.wait(10) # Remember that time this was missing and my desktop fan went nuts? Yeah.

        # Cleanup after the loop ends (i.e., self.stop_flag became true).
        if self.channel:
            self.channel.stop() # Tell the channel to shut up, immediately.
            self.channel.set_endevent() # Clear the event, no more notifications needed.
            self.channel = None # Release the channel for others to use (or for us, next time).
        # self.playing will be set to False in the stop() method that likely triggered this.

    def start(self):
        # "Engage!" - Captain Picard, and this function. My friend got me into star-trek... Patrick Stewart is tired, just let the man rest.
        if not self.playing:
            if not pygame.mixer.get_init():
                # Can't start if the sound system isn't even working.
                print("Cannot start: Pygame mixer not initialized. SAD.")
                if root and hasattr(root, "update_status_display"):
                    root.update_status_display(error_message="Mixer not init for start.")
                return

            self.stop_flag = False # Clear any previous stop requests. We want to GO.
            self.playing = True    # We are now officially "playing" (or trying to).
            self.needs_settings_update = True # Force re-check of settings, important for fresh start.
                                              # And especially for noise generators to reset.

            # Spin up the audio_loop in its own little world (thread).
            # daemon=True means the thread won't prevent the program from exiting. Good manners.
            self.thread = threading.Thread(target=self.audio_loop, daemon=True)
            self.thread.start() # And... action!

    def stop(self):
        # "Make it stop!" - Everyone, eventually.
        # This logic is a bit tricky because stop() can be called from the main thread (GUI)
        # or from the audio thread itself (e.g., on critical error - or as I call it, oh shit.).
        current_thread_is_audio = self.thread and threading.current_thread() == self.thread

        if self.playing or (self.thread and self.thread.is_alive() and not current_thread_is_audio):
            # If we're playing, or if the audio thread exists, is alive, and this call isn't *from* the audio thread...
            self.stop_flag = True # Signal the audio_loop to wind down.
            if self.thread and self.thread.is_alive():
                 # Give the thread a moment to stop gracefully. Don't wait forever.
                 # Timeout is important, otherwise GUI could hang if thread misbehaves.
                 # 0.5 seconds should be plenty for it to notice the stop_flag and exit.
                 self.thread.join(timeout=0.5)
                 # After join, the thread *should* be done. If it's still alive, well, that's a problem
                 # but daemon=True means it won't block program exit.

        self.playing = False # We are officially "not playing" anymore.
        # If stop() is called from within the audio thread, it needs to clean up its own channel.
        # If called from main thread, audio_loop cleans up its channel before exiting.
        # This condition prevents trying to manage channel from main thread if audio thread is doing it.
        if current_thread_is_audio and self.channel:
            self.channel.stop()
            self.channel.set_endevent()
            self.channel = None
        # If not current_thread_is_audio, the audio_loop itself will handle stopping its channel when stop_flag is seen.

    def set_frequency(self, freq_str):
        # User typed in a frequency. Let's see if it's a real number.
        new_freq = float(freq_str) # Could go boom if user types "banana". Handled by caller's try-except.
        if self.frequency != new_freq:
            self.frequency = new_freq
            # Noises don't care about frequency (they are all frequencies!), so only update if it's a tone.
            if self.waveform not in ["white_noise", "pink_noise", "brown_noise"]:
                self.needs_settings_update = True # Tell the generator "Hey, things changed!"

    def set_beat_frequency(self, beat_freq_str):
        # For those groovy binaural beats.
        new_beat_freq = float(beat_freq_str)
        if self.beat_frequency != new_beat_freq:
            self.beat_frequency = new_beat_freq
            if self.waveform == "binaural_beat": # Only matters for binaural beats.
                self.needs_settings_update = True

    def toggle_phase(self):
        # Flip that phase like a pancake!
        self.phase_shift = not self.phase_shift
        # Phase doesn't apply to noise (it's random anyway) or binaural (handled differently, or not at all for simplicity here).
        if self.waveform not in ["white_noise", "pink_noise", "brown_noise", "binaural_beat"]:
            self.needs_settings_update = True # Phase changes means waveform changes.

    def set_volume(self, vol_str):
        # "Turn it up! (or down)"
        new_vol = float(vol_str)
        if self.volume != new_vol:
            self.volume = new_vol
            if self.channel: # If we have a channel, tell it immediately.
                self.channel.set_volume(self.volume)
            # No `needs_settings_update` because volume is applied directly, doesn't change buffer *data*.

    def set_waveform(self, wf_name):
        # A new sound adventure!
        if self.waveform != wf_name:
            self.waveform = wf_name
            self._initialize_noise_states() # CRITICAL for noise: if switching to/from noise, states MUST be reset.
                                            # Spent a good while debugging why noise sounded "stale" after switching. This was it.
            self.needs_settings_update = True # Big change, definitely need to update.
            if root and hasattr(root, "toggle_binaural_controls_active_state"): # If GUI exists...
                root.toggle_binaural_controls_active_state() # Update UI elements accordingly.

# --- GUI Setup ---
# Now for the part you can actually see and click. The "User Interface". Fancy...
player = None # Start with no player, just in case Pygame mixer init failed.
if pygame.mixer.get_init(): # Only make a player if we can actually play sounds.
    player = ToneGenerator() # Tada! One ToneGenerator, ready for action.
else:
    # Sad trombone sound (ironically, we can't play it).
    # The error was printed earlier. Tkinter will show a status message later.
    pass

root = tk.Tk() # The main window. The stage for our little audio drama.
root.title("Leona's Tinnitus Sound Generator") # My name in lights! Or, window titles.

# --- Global Tkinter Variables for Timer ---
# Globals, purists look away! Sometimes, for simple GUI state, they're just easier.
timer_enabled_var = tk.BooleanVar(value=False) # Is the "stop after X minutes" timer on?
timer_duration_minutes_var = tk.IntVar(value=10) # Default 10 mins. Seemed reasonable.
timer_id_var = None # To keep track of Tkinter's `after` event, so we can cancel it.
                    # Forgetting to cancel this led to some "ghost timer" fun in early versions.

# --- GUI Helper Functions ---
# Little worker bees that make the GUI do stuff.

def update_settings_and_status_display(event=None): # `event=None` because Tkinter bindings like to pass an event object.
    # This is the Grand Central Station of UI updates.
    # When a slider moves or a box is ticked, this function gets called to tell the player.
    if not player: # Safety check. If player is None, we're in a bad audio state.
        if hasattr(root, 'update_status_display'): root.update_status_display(error_message="Audio system error.")
        return # Can't do much without a player.

    # Grab all the current settings from the GUI elements.
    freq = freq_var.get()
    beat_freq = beat_freq_var.get()
    vol = volume_var.get()
    selected_waveform = waveform_var.get()

    # Tell the player object about these new, exciting settings.
    player.set_frequency(freq)
    player.set_beat_frequency(beat_freq)
    player.set_volume(vol) # Volume is set directly on channel if playing, this updates player's internal state.
    player.set_waveform(selected_waveform) # This might trigger needs_settings_update in player.

    # Update the display labels to reflect the current reality.
    # User likes to see what they've chosen. Or what the code *thinks* they've chosen.
    current_freq_label.config(text=f"Carrier Freq: {player.frequency:.0f} Hz")
    # Sync entry box if slider changed it, or if player clamped it.
    if str(int(player.frequency)) != freq_entry_var.get():
        freq_entry_var.set(str(int(player.frequency)))

    beat_freq_display_label.config(text=f"Beat Freq: {player.beat_frequency:.1f} Hz")
    current_entry_beat_freq = beat_freq_entry_var.get()
    player_beat_freq_str = f"{player.beat_frequency:.1f}" # Format it consistently.
    try:
        # This try-except is for when the entry box has some nonsense, then slider moves.
        # Or if the player logic changed the value (e.g. clamping).
        if float(current_entry_beat_freq) != player.beat_frequency:
             beat_freq_entry_var.set(player_beat_freq_str)
    except ValueError: # If entry box has "abc", float() fails. Just set it to player's value.
        beat_freq_entry_var.set(player_beat_freq_str)

    volume_display_label.config(text=f"Volume: {int(player.volume*100)}%")
    if hasattr(root, 'update_status_display'): root.update_status_display() # And update the main status bar.

# Attaching functions to 'root' like this is a bit cheeky, but it makes them easily accessible
# from anywhere that has 'root', without passing 'root' around like a hot potato.
# Or, you know, proper class structure for the GUI. But this is "my style".
def root_update_status_display_impl(error_message=None): # Renamed to avoid confusion.
    # This function crafts the informative (or alarming) message at the bottom of the GUI.
    status_text = ""
    if not pygame.mixer.get_init() or not player : # The big "uh oh" for audio.
        status_text = "Status: ERROR - Audio system not available."
    elif error_message: # If a specific error message was passed.
        status_text = f"Status: ERROR - {error_message}"
    elif player.playing:
        # If we're playing, tell the user what glorious noise they're hearing.
        status_text = f"Playing: Vol {player.volume*100:.0f}% | {player.waveform}"
        if player.waveform == "binaural_beat":
            status_text += f" ({player.frequency:.0f}Hz + {player.beat_frequency:.1f}Hz beat)"
        elif player.waveform not in ["white_noise", "pink_noise", "brown_noise"]: # Noises don't have a single frequency.
            status_text += f" ({player.frequency:.0f}Hz)"

        # Phase info, but only if it's relevant.
        if player.waveform not in ["white_noise", "pink_noise", "brown_noise", "binaural_beat"]:
             status_text += f", Phase: {'ON' if player.phase_shift else 'OFF'}"
        if timer_enabled_var.get() and player.playing: # Is the timer countdown active?
            status_text += f" | Timer: ON ({timer_duration_minutes_var.get()} min)"
    else:
        # If not playing, just say "Stopped".
        status_text = "Status: Stopped"
        if timer_enabled_var.get() and timer_id_var: # Timer might be set but sound stopped manually.
            status_text += " (Timer active but playback stopped)"
    status_label.config(text=status_text) # Put the text in the label. Voila.
root.update_status_display = root_update_status_display_impl # Magic attachment!

def toggle_binaural_controls_active_state_impl():
    # This function is the gatekeeper for which controls are enabled or disabled.
    # It's a bit of a spaghetti of conditions, but it mostly works. Mostly.
    # One misplaced 'and' or 'or' here and the UI behaves like it's haunted.
    is_binaural = (waveform_var.get() == "binaural_beat")
    is_noise = waveform_var.get() in ["white_noise", "pink_noise", "brown_noise"]
    audio_ok = pygame.mixer.get_init() and player is not None # Is audio even functional?

    # Default state: if audio is okay, things are NORMAL. Otherwise, DISABLED.
    global_state = tk.NORMAL if audio_ok else tk.DISABLED

    # Binaural beat frequency controls: only active if "binaural_beat" is chosen AND audio is OK.
    binaural_state = tk.NORMAL if is_binaural and audio_ok else tk.DISABLED
    beat_freq_slider.config(state=binaural_state)
    beat_freq_entry.config(state=binaural_state)
    beat_freq_label_text.config(state=global_state) # The label "Beat Freq (Hz):" itself.
    beat_freq_display_label.config(state=binaural_state) # The value display.

    # Carrier frequency controls: disabled for noise types, or if audio is bad.
    tone_freq_state = tk.NORMAL if not is_noise and audio_ok else tk.DISABLED
    freq_slider.config(state=tone_freq_state)
    freq_entry.config(state=tone_freq_state)

    # Phase button: disabled for noise, binaural, or if audio is bad.
    # This logic drove me nuts for a while. "Why is the phase button still active for white noise?!"
    # Many print statements and much caffeine later, it was tamed.
    phase_button_state = tk.NORMAL if not is_noise and not is_binaural and audio_ok else tk.DISABLED
    phase_button.config(state=phase_button_state)

    # If audio is not okay, go on a disabling spree for other crucial controls.
    if not audio_ok:
        freq_slider.config(state=tk.DISABLED) # Already covered by tone_freq_state, but belt and braces.
        freq_entry.config(state=tk.DISABLED)
        # waveform_menu.config(state=tk.DISABLED) # Decided to leave this enabled so user can see options, even if they don't play.
        volume_slider.config(state=tk.DISABLED)
        play_button.config(state=tk.DISABLED) # Can't play if there's no audio, captain, or is it admiral now?
root.toggle_binaural_controls_active_state = toggle_binaural_controls_active_state_impl # More attachment magic.

def on_freq_entry_change(event=None, var_to_set=None, entry_var=None, min_val=0, max_val=20000, is_float=False):
    # Handles when the user types into those little frequency entry boxes.
    # Users, bless their hearts, will type anything. "potato", "99999999", "".
    if not player: return # No player, no glory.
    try:
        val_str = entry_var.get()
        val = float(val_str) if is_float else int(val_str) # Parse as float or int.
        if min_val <= val <= max_val: # Is it in a sensible range?
            var_to_set.set(val) # If yes, update the corresponding Tkinter variable (which updates the slider).
            update_settings_and_status_display() # Then tell everyone else.
        else:
            # If out of range, gently revert the entry box to the last valid value (from the Tkinter var).
            # This prevents the UI from getting stuck with an invalid number.
            current_val = var_to_set.get()
            entry_var.set(f"{current_val:.1f}" if is_float else str(int(current_val)))
    except ValueError:
        # If they typed "banana" (ValueError), also revert to last valid value.
        # "Nice try, user, but this box only accepts numbers now."
        current_val = var_to_set.get()
        entry_var.set(f"{current_val:.1f}" if is_float else str(int(current_val)))

def play_action():
    # The big "PLAY" button action. Let the noises commence!
    global timer_id_var # We might mess with the global timer ID.
    if not player:
        # This should ideally be prevented by disabling the play button, but defense in depth!
        messagebox.showerror("Audio Error", "Audio system not initialized. Cannot play. This is awkward.")
        return

    update_settings_and_status_display() # Make sure player has the latest settings from UI.
    player.start() # Tell the player to do its thing.

    # Timer logic: if a timer was already running, cancel it. We're starting fresh.
    if timer_id_var:
        root.after_cancel(timer_id_var)
        timer_id_var = None # Important to nullify it.

    if timer_enabled_var.get(): # If the user wants a timer...
        duration_ms = timer_duration_minutes_var.get() * 60 * 1000 # Convert minutes to milliseconds.
        if duration_ms > 0: # Don't set a timer for 0 or negative time. That's just silly.
            # Tell Tkinter: "Hey, after this many milliseconds, call stop_action_for_timer."
            timer_id_var = root.after(duration_ms, stop_action_for_timer)
    root.update_status_display() # Update status to show "Playing" and timer info. Hell Yeah! Boi!!! this works.

def stop_action_for_timer():
    # This function is called automatically when the playback timer expires.
    global timer_id_var
    if player: player.stop() # Stop the audio.
    timer_id_var = None # Timer has done its job, clear the ID.
    root.update_status_display() # Update status.
    messagebox.showinfo("Playback Timer", "Playback finished due to timer. Hope your ears feel better!")

def stop_action():
    # Called when the user clicks the "Stop" button.
    global timer_id_var
    if player: player.stop() # Politely ask the player to cease.
    if timer_id_var: # If a timer was running...
        root.after_cancel(timer_id_var) # ...cancel it. User wants to stop NOW.
        timer_id_var = None
    root.update_status_display() # Update status to "Stopped".

def toggle_phase_action():
    # User clicked the phase shift button. Let's flip it!
    if not player: return # Again, if no player, do nothing.
    # Only makes sense for certain waveforms.
    if player.waveform not in ["white_noise", "pink_noise", "brown_noise", "binaural_beat"]:
        player.toggle_phase() # Tell the player object.
        # Update button text to reflect new state. ON/OFF. Clear and simple.
        phase_button.config(text=f"Phase Shift: {'ON' if player.phase_shift else 'OFF'}")
        root.update_status_display() # And the main status bar.

# --- Presets Functions ---
# For the user who finds their perfect tinnitus-cancelling sound and wants to remember it.
def save_preset():
    if not player: # Can't save if there's nothing to save from.
        messagebox.showerror("Error", "Cannot save preset, audio system not ready. Try again when it's less confused.")
        return
    # Ask the user where they want to save this precious preset.
    filepath = filedialog.asksaveasfilename(
        defaultextension=".json", # We like JSON. It's human-readable (mostly).
        filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        title="Save Preset As (don't forget this one!)"
    )
    if not filepath: return # User cancelled. Fair enough.

    # Gather all the important settings into a dictionary.
    settings = {
        "frequency": player.frequency,
        "beat_frequency": player.beat_frequency,
        "volume": player.volume,
        "waveform": player.waveform,
        "phase_shift": player.phase_shift,
        "timer_enabled": timer_enabled_var.get(), # Also save timer settings, why not.
        "timer_duration_minutes": timer_duration_minutes_var.get()
    }
    try:
        # Write the dictionary to a JSON file. Pretty-printed with indent=4, because we're civilized.
        with open(filepath, 'w') as f: json.dump(settings, f, indent=4)
        messagebox.showinfo("Preset Saved", f"Preset saved to {filepath}. Phew.")
    except Exception as e:
        # Something went wrong. File permissions? Disk full? Gremlins?
        messagebox.showerror("Error Saving Preset", f"Could not save preset: {e}. The computer says no.")

def load_preset():
    if not player: # Again, check for player.
        messagebox.showerror("Error", "Cannot load preset, audio system not ready. It's having a moment.")
        return
    # Ask user which masterpiece of a preset they wish to recall.
    filepath = filedialog.askopenfilename(
        defaultextension=".json",
        filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        title="Load Preset (choose wisely)"
    )
    if not filepath: return # User bailed. Okay.

    try:
        # Read the JSON file.
        with open(filepath, 'r') as f: settings = json.load(f)

        # Apply the settings from the file to our Tkinter variables and player state.
        # .get() with a default value is nice, in case a preset is old or missing a key.
        freq_var.set(settings.get("frequency", 440.0))
        beat_freq_var.set(settings.get("beat_frequency", 4.0))
        volume_var.set(settings.get("volume", 0.8))
        waveform_var.set(settings.get("waveform", "sine")) # This will trigger its own update via bind.

        # Phase shift is a direct player attribute, not a Tkinter var.
        player.phase_shift = settings.get("phase_shift", False)
        phase_button.config(text=f"Phase Shift: {'ON' if player.phase_shift else 'OFF'}") # Update button text.

        # Timer settings.
        timer_enabled_var.set(settings.get("timer_enabled", False))
        timer_duration_minutes_var.set(settings.get("timer_duration_minutes", 10))

        update_settings_and_status_display() # Make all these changes take effect and update UI.
        messagebox.showinfo("Preset Loaded", f"Preset loaded from {filepath}. Let the healing (or noise) begin!")
    except Exception as e:
        # File not found? Corrupt JSON? Wrong file type?
        messagebox.showerror("Error Loading Preset", f"Could not load preset: {e}. Maybe it's written in Klingon?")

# --- Main Window Layout ---
# Time to build the GUI, brick by brick. Or widget by widget.
# This is where Tkinter's "pack" geometry manager gets its workout.
# Sometimes it feels like wrestling an octopus. No, not like a normal octopus, one of those ones in a Japanese cartoon.

# Presets Buttons
preset_frame = ttk.Frame(root) # A frame to hold the preset buttons. Tidy.
preset_frame.pack(pady=5, fill="x", padx=5)
ttk.Button(preset_frame, text="Save Preset", command=save_preset).pack(side=tk.LEFT, padx=10)
ttk.Button(preset_frame, text="Load Preset", command=load_preset).pack(side=tk.LEFT, padx=10)

# --- Frequency Controls ---
freq_main_frame = ttk.LabelFrame(root, text="Tone Settings") # A nice labeled box.
freq_main_frame.pack(pady=5, padx=5, fill="x")

freq_frame = ttk.Frame(freq_main_frame) # Sub-frame for the actual controls.
freq_frame.pack(pady=2, fill="x", expand=True)
ttk.Label(freq_frame, text="Carrier Freq (Hz):").pack(side=tk.LEFT, padx=5)
# The player might not exist if audio init failed. So, sensible defaults.
freq_var = tk.DoubleVar(value=player.frequency if player else 440.0)
freq_slider = ttk.Scale(freq_frame, from_=20, to=15000, variable=freq_var, orient="horizontal", length=180, command=update_settings_and_status_display)
freq_slider.pack(side=tk.LEFT, padx=5, fill="x", expand=True) # fill and expand are my best friends here.
freq_entry_var = tk.StringVar(value=str(int(player.frequency if player else 440.0)))
freq_entry = ttk.Entry(freq_frame, textvariable=freq_entry_var, width=7) # Small box for precise numbers.
freq_entry.pack(side=tk.LEFT, padx=5)
# Bind <Return> (Enter key) and <FocusOut> (clicking away) to update from the entry box.
# Lambdas, because sometimes you need a quick, disposable function.
freq_entry.bind("<Return>", lambda e: on_freq_entry_change(e, freq_var, freq_entry_var, 20, 15000))
freq_entry.bind("<FocusOut>", lambda e: on_freq_entry_change(e, freq_var, freq_entry_var, 20, 15000))
current_freq_label = ttk.Label(freq_main_frame, text=f"Carrier Freq: {(player.frequency if player else 440.0):.0f} Hz")
current_freq_label.pack(pady=2) # Shows the current value numerically.

# --- Binaural Beat Frequency Controls ---
# Pretty much a copy-paste of the carrier frequency controls, but for beat frequency.
# DRY principle? What's that? (Just kidding... mostly.)
beat_freq_frame = ttk.Frame(freq_main_frame)
beat_freq_frame.pack(pady=2, fill="x", expand=True)
beat_freq_label_text = ttk.Label(beat_freq_frame, text="Beat Freq (Hz):") # Storing this to enable/disable label text (though state on Label is tricky)
beat_freq_label_text.pack(side=tk.LEFT, padx=5)
beat_freq_var = tk.DoubleVar(value=player.beat_frequency if player else 4.0)
beat_freq_slider = ttk.Scale(beat_freq_frame, from_=0.1, to=30.0, variable=beat_freq_var, orient="horizontal", length=180, command=update_settings_and_status_display)
beat_freq_slider.pack(side=tk.LEFT, padx=5, fill="x", expand=True)
beat_freq_entry_var = tk.StringVar(value=f"{(player.beat_frequency if player else 4.0):.1f}") # Needs .1f for float.
beat_freq_entry = ttk.Entry(beat_freq_frame, textvariable=beat_freq_entry_var, width=7)
beat_freq_entry.pack(side=tk.LEFT, padx=5)
beat_freq_entry.bind("<Return>", lambda e: on_freq_entry_change(e, beat_freq_var, beat_freq_entry_var, 0.1, 30.0, is_float=True))
beat_freq_entry.bind("<FocusOut>", lambda e: on_freq_entry_change(e, beat_freq_var, beat_freq_entry_var, 0.1, 30.0, is_float=True))
beat_freq_display_label = ttk.Label(freq_main_frame, text=f"Beat Freq: {(player.beat_frequency if player else 4.0):.1f} Hz")
beat_freq_display_label.pack(pady=2)

# --- Waveform Selection ---
waveform_frame = ttk.LabelFrame(root, text="Sound Type")
waveform_frame.pack(pady=5, padx=5, fill="x")
ttk.Label(waveform_frame, text="Waveform:").pack(side=tk.LEFT, padx=5)
waveforms = ["sine", "square", "sawtooth", "triangle", "white_noise", "pink_noise", "brown_noise", "binaural_beat"] # All our lovely sounds.
waveform_var = tk.StringVar(value=player.waveform if player else "sine")
# A Combobox (dropdown menu). state="readonly" means user can't type in custom values. Wise.
waveform_menu = ttk.Combobox(waveform_frame, textvariable=waveform_var, values=waveforms, state="readonly", width=15)
waveform_menu.pack(side=tk.LEFT, padx=5, pady=5)
waveform_menu.bind("<<ComboboxSelected>>", update_settings_and_status_display) # Special event for combobox.

# --- Volume Control ---
# Similar setup for volume. Slider and a label.
volume_frame = ttk.LabelFrame(root, text="Output Level")
volume_frame.pack(pady=5, padx=5, fill="x")
ttk.Label(volume_frame, text="Volume:").pack(side=tk.LEFT, padx=5)
volume_var = tk.DoubleVar(value=player.volume if player else 0.8)
volume_slider = ttk.Scale(volume_frame, from_=0.0, to=1.0, variable=volume_var, orient="horizontal", length=150, command=update_settings_and_status_display)
volume_slider.pack(side=tk.LEFT, padx=5, fill="x", expand=True)
volume_display_label = ttk.Label(volume_frame, text=f"Volume: {int((player.volume if player else 0.8)*100)}%") # Show as percentage.
volume_display_label.pack(side=tk.LEFT, padx=5)

# --- Phase Shift Button ---
# Just a lonely button for toggling phase.
initial_phase_text = "OFF"
if player and player.phase_shift: # Check if player exists before accessing attributes.
    initial_phase_text = "ON"
phase_button = ttk.Button(root, text=f"Phase Shift: {initial_phase_text}", command=toggle_phase_action)
phase_button.pack(pady=5)

# --- Timer Controls ---
timer_frame = ttk.LabelFrame(root, text="Playback Timer")
timer_frame.pack(pady=5, padx=5, fill="x")
# Checkbox to turn timer on/off. Command updates status bar immediately.
timer_enable_checkbox = ttk.Checkbutton(timer_frame, text="Enable Timer", variable=timer_enabled_var, command=root.update_status_display)
timer_enable_checkbox.pack(side=tk.LEFT, padx=5)
ttk.Label(timer_frame, text="Duration (min):").pack(side=tk.LEFT, padx=5)
timer_duration_entry = ttk.Entry(timer_frame, textvariable=timer_duration_minutes_var, width=5) # For timer length.
timer_duration_entry.pack(side=tk.LEFT, padx=5)

# --- Play/Stop Buttons ---
controls_frame = ttk.Frame(root) # Frame to group Play/Stop.
controls_frame.pack(pady=10)
s = ttk.Style() # For making the Play button look a bit more... playful.
s.configure('Accent.TButton', font=('Helvetica', 10, 'bold'), foreground='green') # Green for GO!
play_button = ttk.Button(controls_frame, text="Play", command=play_action, style="Accent.TButton") # Store for disabling later.
play_button.pack(side=tk.LEFT, padx=10)
ttk.Button(controls_frame, text="Stop", command=stop_action).pack(side=tk.LEFT, padx=10) # Stop is just a regular button.

# --- Status Label ---
# The all-important status bar at the bottom. Tells you what's (supposedly) happening.
status_label = ttk.Label(root, text="Status: Initializing...", relief=tk.SUNKEN, anchor=tk.W, padding=(5,5))
status_label.pack(pady=10, fill="x", expand=True, ipady=5) # ipady makes it a bit taller.

# --- Closing Protocol ---
# What to do when the user clicks the 'X' button on the window.
def on_closing():
    global timer_id_var # We might need to cancel a timer.
    if timer_id_var:
        try:
            root.after_cancel(timer_id_var) # Politely ask Tkinter to forget the timer.
        except tk.TclError: # If root is already being destroyed, this can fail. Shrug.
            pass # "It's fine, everything's fine."
    if player: player.stop() # Crucial: stop the audio thread before exiting!
                             # Otherwise, it might keep playing like a ghost. Spooky.
    root.destroy() # Close the Tkinter window.

root.protocol("WM_DELETE_WINDOW", on_closing) # "Hey Tkinter, when they click 'X', call this function."

# Initial UI state updates after root and all widgets are created.
# "Okay, everyone get to your starting positions!"
root.update_status_display() # Show initial status.
root.toggle_binaural_controls_active_state() # Enable/disable controls based on default settings.

root.mainloop() # And... start the Tkinter event loop! This is where the GUI magic happens.
                # Or, where it waits for user input, patiently.

# --- Cleanup at the very end ---
# After root.mainloop() finishes (i.e., window closed and on_closing run).
if pygame.mixer.get_init(): # Only quit if it was initialized.
    pygame.mixer.quit()     # Tell Pygame mixer "Good night."
if pygame.get_init():       # Check main Pygame init too.
    pygame.quit()           # "And good night to Pygame itself."
# Okay I am done here. I am also out of jokes.
# Good night my sweet prince.
