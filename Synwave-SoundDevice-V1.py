# --- START OF FILE SynWave.py ---

# Oh, look, imports. The usual suspects. Tkinter for the pretty (?) bits,
# struct for when we need to speak in tongues (binary) - actually, not anymore with numpy!
# math because numbers, threading because apparently one thing at a time is for chumps (though sounddevice handles some of this now),
# time for... well, time, os for... actually, are we even using os directly? (Spoiler: No, but it feels important to have)
# NO MORE PYGAME! We're using sounddevice and numpy for the NOISE now.
# random for when we don't know what we're doing,
# and json because saving settings in hieroglyphics was frowned upon.
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
# import struct # Not needed for audio generation anymore!
import math
import threading # Still used for GUI related 'after' calls, and player's own logic if any.
import time
import os # Still here, like an appendix. Useful if it bursts, I guess.
import random
import json

# --- Sounddevice and Numpy for Audio ---
# The moment of truth. We're going to try and poke the audio hardware with a stick.
# If it pokes back, great! If not, well, at least we have a pretty GUI.
SOUNDDEVICE_AVAILABLE = False # Let's start with crippling pessimism. It's safer that way.
SD_ERROR_MESSAGE = "" # An empty vessel for our future tears and error messages.

try:
    # Attempt to summon the spirits of sound. Sounddevice is the vocalist,
    # and Numpy is the roadie who does all the heavy lifting (of numbers).
    import sounddevice as sd
    import numpy as np

    # First, a gentle probe. "Excuse me, Mr. Sounddevice, do you happen to see any speakers?"
    # This doesn't guarantee they work, but it's a good sign if they're not invisible.
    if not sd.query_devices(kind='output'):
        SD_ERROR_MESSAGE = "No output audio devices found by Sounddevice."
        # We don't panic just yet. The default device might be a mysterious hermit that still answers when called.

    # Now for the real test. This is the bouncer at the club door.
    # It will throw a fit (an Exception) if there's no way to actually play sound.
    sd.check_output_settings()

    # If we made it this far without an explosion, we're golden!
    SOUNDDEVICE_AVAILABLE = True
    print("Sounddevice library found and appears functional.")
except Exception as e:
    # Aaaand there's the explosion. The bouncer said no.
    # We catch the error, write a sad little note for the user, and accept our silent fate.
    SD_ERROR_MESSAGE = f"Could not initialize Sounddevice: {e}\n"\
                       "Please ensure 'sounddevice' and 'numpy' are installed, and PortAudio is available.\n"\
                       "Audio playback will be disabled."
    print(f"CRITICAL AUDIO ERROR: {SD_ERROR_MESSAGE}")


# --- Constants ---
# Ah, constants. The things we swear we'll never change, until we do.
SAMPLE_RATE = 44100 # Still a good number. Sounddevice will use this.
# BUFFER_DURATION is now used to calculate blocksize for sounddevice callbacks.
# A shorter duration means more frequent callbacks, potentially lower latency but more overhead.
BUFFER_DURATION = 0.05  # seconds. Let's try a bit shorter for sounddevice.
                        # This will define our 'blocksize' for the audio callback.


class ToneGenerator:
    # Behold! The ToneGenerator! The glorious machine that turns numbers into noise.
    # Now upgraded to the SoundDevice model. Less Pygame hacking, more... science?
    # This class holds all the knobs, dials, and secret ingredients for our sound concoctions.
    def __init__(self):
        # Default settings... for when you first open the app and just want to make a bleep.
        self.frequency = 440.0          # A classic A4. The most agreeable of frequencies.
        self.beat_frequency = 4.0       # For those trendy binaural brain-ticklers.
        self.phase_shift = False        # The "flip the wave upside-down" switch. Why? For science!
        self.playing = False            # A simple question: are we currently making a racket?
        # self.thread = None # The old audio_loop thread is gone. Sounddevice is the captain now.
        self.stop_flag = False          # Still our "PLEASE, FOR THE LOVE OF ALL THAT IS HOLY, MAKE IT STOP" flag.
        self.volume = 0.8               # Volume, now applied directly to the samples. 1.0 is MAX, try not to deafen yourself.
        self.waveform = "sine"          # Starting with the smoothest operator of all waveforms.

        # This is the new magic wand. It's our direct line to the sound card, courtesy of Sounddevice.
        self.stream = None
        # This is our little messenger flag. It tells the high-speed audio thread, "Hey, the user changed something, you need to reset."
        self.needs_settings_update = True

        # To avoid nasty clicks between audio chunks, we need to remember where we left off. This is our bookmark in the river of time.
        self.current_time_offset = 0.0

        # Frequency Sweep Attributes... the knobs for the "wub-wub-wub" machine.
        self.sweep_start_freq = 200.0   # Where the whoop starts.
        self.sweep_end_freq = 800.0     # Where the whoop ends.
        self.sweep_duration_one_way = 5.0 # How long it takes to get from one to the other.
        self.swept_waveform = "sine"    # The shape of the whoop itself.
        # These next ones are the internal cogs of the sweep machine. Don't touch, just admire.
        self.sweep_phase_accumulator = 0.0 # Like current_time_offset, but for a constantly changing frequency. It's complicated.
        self.sweep_current_val = 0.0       # How far along we are in the current sweep (from 0.0 to 1.0).
        self.sweep_direction = 1           # Are we going up (1) or down (-1)?
        self.sweep_current_freq_actual = self.sweep_start_freq # So the GUI can tell the user what's happening right NOW.

        # The number of output channels for the stream. We're living in the future, so let's default to stereo.
        # If we make a mono sound, we'll just be lazy and copy it to both channels.
        self.stream_channels = 2

        # Gotta set up the noise generators right away. They're a bit... stateful.
        self._initialize_noise_states()

    def _initialize_noise_states(self):
        # This is the "factory reset" button for our noise generators.
        # Pink and Brown noise are special; they have 'memory'. Each sample depends on the last one.
        # So when we start or switch to them, we need to wipe their brains.
        self.last_brown_sample_norm = 0.0           # Reset the "random walk" of the brown noise.
        self.pink_b = np.zeros(7, dtype=np.float32) # Clear out the magic filter values for pink noise.
        self.current_time_offset = 0.0              # While we're at it, let's reset the main clock so other waves also start fresh.

    def _initialize_sweep_state(self):
        # And this is the factory reset for the frequency sweep.
        # We need this to make sure that every time we hit play on a sweep, it starts from the beginning,
        # not from some weird, forgotten point in the middle of a whoop.
        print("DEBUG: Initializing sweep state (phase acc, current val, direction)")
        self.sweep_phase_accumulator = 0.0  # Forget the old phase.
        self.sweep_current_val = 0.0        # Go back to the start of the ramp.
        self.sweep_direction = 1            # Always start by going up.
        self.sweep_current_freq_actual = self.sweep_start_freq # The "current frequency" is now the start frequency.
        self.current_time_offset = 0.0      # Reset the main clock too, just for consistency. Can't hurt.

    def set_sweep_params(self, start_freq_str, end_freq_str, duration_str, swept_waveform_type):
        # This function is the long-suffering receptionist for the sweep settings.
        # It takes the strings the user typed in the GUI and tries to make sense of them.
        changed = False # Assume nothing has changed, prove me wrong.
        try:
            # Attempt to convert the user's potentially nonsensical input into glorious numbers.
            new_start_freq = float(start_freq_str)
            new_end_freq = float(end_freq_str)
            new_duration = float(duration_str)

            # Now check if any of the numbers are actually different from what we already have.
            # No point in bothering the audio engine if the user just re-typed the same value.
            if self.sweep_start_freq != new_start_freq:
                self.sweep_start_freq = new_start_freq
                changed = True
            if self.sweep_end_freq != new_end_freq:
                self.sweep_end_freq = new_end_freq
                changed = True
            if self.sweep_duration_one_way != new_duration:
                # Don't let them enter a duration of zero. That's just asking for a divide-by-zero apocalypse.
                self.sweep_duration_one_way = max(0.1, new_duration)
                changed = True
            if self.swept_waveform != swept_waveform_type:
                self.swept_waveform = swept_waveform_type
                changed = True

            if changed:
                # Aha! Something changed! Hoist the "needs_settings_update" flag
                # to let the audio thread know it needs to re-read the instructions.
                print(f"DEBUG: Sweep params changed via GUI. Triggering needs_settings_update.")
                self.needs_settings_update = True
            return True
        except ValueError:
            # The user typed "potato" into a frequency box. Of course they did.
            # We just ignore it and move on with our lives.
            print(f"Error: Invalid sweep parameter format.")
            return False

    # --- Waveform Sample Generation (these now return float samples, not int) ---
    # Amplitude for these helpers is 1.0; final volume applied later or in generate_audio_buffer.

    def _generate_sine_sample_float(self, current_freq, time_val_or_angle, amplitude, phase_shifted, is_angle=False):
        # Can take pre-calculated angle (for sweep) or time_val (for fixed freq)
        if is_angle:
            angle = time_val_or_angle
        else:
            angle = 2.0 * math.pi * current_freq * time_val_or_angle

        if phase_shifted:
            angle += math.pi
        return amplitude * math.sin(angle)

    def _generate_square_sample_float(self, current_freq, time_val_or_angle, amplitude, phase_shifted, is_angle=False):
        if is_angle:
            angle = time_val_or_angle
        else:
            angle = 2.0 * math.pi * current_freq * time_val_or_angle

        if phase_shifted:
            angle += math.pi
        return amplitude if math.sin(angle) >= 0 else -amplitude

    def _generate_sawtooth_sample_float(self, current_freq, time_val_or_angle, amplitude, phase_shifted, is_angle=False):
        if is_angle:
            norm_phase = (time_val_or_angle / (2.0 * math.pi)) % 1.0
        else:
            norm_phase = (current_freq * time_val_or_angle) % 1.0

        if phase_shifted:
            norm_phase = (norm_phase + 0.5) % 1.0
        return amplitude * ((2.0 * norm_phase) - 1.0)

    def _generate_triangle_sample_float(self, current_freq, time_val_or_angle, amplitude, phase_shifted, is_angle=False):
        if is_angle:
            norm_phase = (time_val_or_angle / (2.0 * math.pi)) % 1.0
        else:
            norm_phase = (current_freq * time_val_or_angle) % 1.0

        if phase_shifted:
            norm_phase = (norm_phase + 0.5) % 1.0

        val_norm = 0.0
        if norm_phase < 0.5: val_norm = (4.0 * norm_phase) - 1.0
        else: val_norm = 3.0 - (4.0 * norm_phase)
        return amplitude * val_norm

    def _generate_white_noise_sample_float(self, amplitude):
        return amplitude * random.uniform(-1.0, 1.0)

    def _generate_pink_noise_sample_float(self, amplitude):
        # Using numpy for state array now
        white = random.uniform(-1.0, 1.0)
        self.pink_b[0] = 0.99886 * self.pink_b[0] + white * 0.0555179
        self.pink_b[1] = 0.99332 * self.pink_b[1] + white * 0.0750759
        self.pink_b[2] = 0.96900 * self.pink_b[2] + white * 0.1538520
        self.pink_b[3] = 0.86650 * self.pink_b[3] + white * 0.3104856
        self.pink_b[4] = 0.55000 * self.pink_b[4] + white * 0.5329522
        self.pink_b[5] = -0.7616 * self.pink_b[5] - white * 0.0168980
        pink_val_sum = np.sum(self.pink_b[:6]) + self.pink_b[6] + white * 0.5362 # Corrected sum
        self.pink_b[6] = white * 0.115926
        normalized_pink = pink_val_sum / 5.5
        clamped_pink = max(-1.0, min(1.0, normalized_pink))
        return amplitude * clamped_pink

    def _generate_brown_noise_sample_float(self, amplitude):
        white = random.uniform(-1.0, 1.0)
        self.last_brown_sample_norm += white * 0.02
        self.last_brown_sample_norm = max(-1.0, min(1.0, self.last_brown_sample_norm))
        return amplitude * self.last_brown_sample_norm


    def generate_audio_buffer(self, num_frames_to_generate):
        # This is where we cook up a batch of sound, now as a NumPy array!
        # print(f"DEBUG: generate_audio_buffer for {num_frames_to_generate} frames, waveform: {self.waveform}")

        # Max amplitude for float32 samples is 1.0. Volume is applied at the end.
        _amplitude_float = 1.0

        # Initialize an empty NumPy array for our samples.
        # Shape will be (num_frames, self.stream_channels)
        # For now, assuming self.stream_channels is consistently 2 (stereo).
        buffer_out = np.zeros((num_frames_to_generate, self.stream_channels), dtype=np.float32)

        # The grand "if-elif-else" chain of sound generation.
        if self.waveform == "frequency_sweep":
            valid_sweep_duration = max(0.001, self.sweep_duration_one_way)
            current_leg_origin_freq, current_leg_target_freq = (self.sweep_start_freq, self.sweep_end_freq) if self.sweep_direction == 1 else (self.sweep_end_freq, self.sweep_start_freq)
            delta_freq_current_leg = current_leg_target_freq - current_leg_origin_freq

            for i in range(num_frames_to_generate):
                inst_freq = current_leg_origin_freq + (delta_freq_current_leg * self.sweep_current_val)
                self.sweep_current_freq_actual = inst_freq
                self.sweep_phase_accumulator += (2.0 * math.pi * inst_freq) / SAMPLE_RATE
                angle_for_sample_gen = self.sweep_phase_accumulator # Phase shift applied in helper

                sample_val = 0.0
                if self.swept_waveform == "sine":
                    sample_val = self._generate_sine_sample_float(0, angle_for_sample_gen, _amplitude_float, self.phase_shift, is_angle=True)
                elif self.swept_waveform == "square":
                    sample_val = self._generate_square_sample_float(0, angle_for_sample_gen, _amplitude_float, self.phase_shift, is_angle=True)
                elif self.swept_waveform == "sawtooth":
                    sample_val = self._generate_sawtooth_sample_float(0, angle_for_sample_gen, _amplitude_float, self.phase_shift, is_angle=True)
                elif self.swept_waveform == "triangle":
                    sample_val = self._generate_triangle_sample_float(0, angle_for_sample_gen, _amplitude_float, self.phase_shift, is_angle=True)

                buffer_out[i, 0] = sample_val # Left channel
                buffer_out[i, 1] = sample_val # Right channel (mono sweep to stereo)

                time_increment_per_sample = 1.0 / SAMPLE_RATE
                progress_increment_per_sample = time_increment_per_sample / valid_sweep_duration
                self.sweep_current_val += progress_increment_per_sample
                if self.sweep_current_val >= 1.0:
                    self.sweep_current_val -= 1.0
                    self.sweep_direction *= -1

        elif self.waveform == "binaural_beat":
            for i in range(num_frames_to_generate):
                time_val = self.current_time_offset + (i / SAMPLE_RATE)
                left_ear_freq = self.frequency
                right_ear_freq = self.frequency + self.beat_frequency
                buffer_out[i, 0] = self._generate_sine_sample_float(left_ear_freq, time_val, _amplitude_float, self.phase_shift)
                buffer_out[i, 1] = self._generate_sine_sample_float(right_ear_freq, time_val, _amplitude_float, self.phase_shift) # Binaural uses same phase_shift for both

        else: # All other waveforms are mono, will be duplicated to stereo
            mono_samples = np.zeros(num_frames_to_generate, dtype=np.float32)
            if self.waveform == "sine":
                for i in range(num_frames_to_generate):
                    time_val = self.current_time_offset + (i / SAMPLE_RATE)
                    mono_samples[i] = self._generate_sine_sample_float(self.frequency, time_val, _amplitude_float, self.phase_shift)
            elif self.waveform == "square":
                for i in range(num_frames_to_generate):
                    time_val = self.current_time_offset + (i / SAMPLE_RATE)
                    mono_samples[i] = self._generate_square_sample_float(self.frequency, time_val, _amplitude_float, self.phase_shift)
            elif self.waveform == "sawtooth":
                for i in range(num_frames_to_generate):
                    time_val = self.current_time_offset + (i / SAMPLE_RATE)
                    mono_samples[i] = self._generate_sawtooth_sample_float(self.frequency, time_val, _amplitude_float, self.phase_shift)
            elif self.waveform == "triangle":
                for i in range(num_frames_to_generate):
                    time_val = self.current_time_offset + (i / SAMPLE_RATE)
                    mono_samples[i] = self._generate_triangle_sample_float(self.frequency, time_val, _amplitude_float, self.phase_shift)
            elif self.waveform == "white_noise":
                for i in range(num_frames_to_generate):
                    mono_samples[i] = self._generate_white_noise_sample_float(_amplitude_float)
            elif self.waveform == "pink_noise":
                for i in range(num_frames_to_generate):
                    mono_samples[i] = self._generate_pink_noise_sample_float(_amplitude_float)
            elif self.waveform == "brown_noise":
                for i in range(num_frames_to_generate):
                    mono_samples[i] = self._generate_brown_noise_sample_float(_amplitude_float)

            buffer_out[:, 0] = mono_samples # Copy mono to Left channel
            buffer_out[:, 1] = mono_samples # Copy mono to Right channel

        # Apply volume to the entire buffer
        buffer_out *= self.volume

        # Advance time offset for non-sweep waveforms
        if self.waveform not in ["frequency_sweep"]:
            self.current_time_offset += num_frames_to_generate / SAMPLE_RATE
            if self.current_time_offset > 3600.0:
                 self.current_time_offset -= 3600.0

        return buffer_out

    def _audio_callback(self, outdata: np.ndarray, frames: int, time_info, status: sd.CallbackFlags):
        # This function is called by sounddevice when it needs more audio data.
        # It runs in a separate thread, so be careful with shared state!
        if status:
            print(f"Sounddevice callback status: {status}", flush=True) # Report underruns/overruns etc.

        if self.stop_flag:
            print("DEBUG: Stop flag active in audio callback. Outputting silence and stopping stream.")
            outdata[:] = 0 # Fill with silence
            raise sd.CallbackStop # Tell sounddevice to stop calling us.

        # Thread-safety consideration: `needs_settings_update` is set by GUI thread.
        # If it's true, re-initialize states. This should ideally be atomic or locked
        # if state initialization is complex and could race. For now, it's simple.
        # A lock (`threading.Lock`) around access to `needs_settings_update` and sensitive state variables
        # would be more robust if issues arise.
        if self.needs_settings_update:
            # print("DEBUG: needs_settings_update detected in _audio_callback.")
            if self.waveform in ["white_noise", "pink_noise", "brown_noise"]:
                self._initialize_noise_states()
            elif self.waveform == "frequency_sweep":
                self._initialize_sweep_state()
            # For standard tones, changing frequency/phase just uses new values.
            # current_time_offset continues unless reset by a waveform change or state init.
            self.needs_settings_update = False # Reset flag after handling.

        try:
            buffer_to_play = self.generate_audio_buffer(frames)
            if buffer_to_play is not None and buffer_to_play.shape == outdata.shape:
                outdata[:] = buffer_to_play
            else:
                # This case should ideally not happen if generate_audio_buffer is correct.
                print(f"Error: Buffer shape mismatch or None. Expected {outdata.shape}, got {buffer_to_play.shape if buffer_to_play is not None else 'None'}. Outputting silence.")
                outdata[:] = 0 # Silence
        except Exception as e:
            print(f"CRITICAL ERROR in audio generation or callback: {e}. Outputting silence.")
            # Potentially stop the stream or log more details
            outdata[:] = 0 # Silence
            # Consider raising sd.CallbackAbort if error is unrecoverable.

    def start(self):
        # "Engage! (with SoundDevice)"
        if self.playing:
            return

        if not SOUNDDEVICE_AVAILABLE:
            print("Cannot start: Sounddevice not available.")
            if root and hasattr(root, "update_status_display"):
                root.update_status_display(error_message="Sounddevice not available.")
            return

        self.stop_flag = False
        self.playing = True
        self.needs_settings_update = True # Force re-check/re-init of states for the first buffer.

        # blocksize is the number of frames per callback.
        block_size = int(SAMPLE_RATE * BUFFER_DURATION)
        if block_size == 0: block_size = None # Let sounddevice choose if duration is too small.

        try:
            # Ensure any previous stream is closed (should be handled by stop(), but defense)
            if self.stream and not self.stream.closed:
                print("Warning: Previous stream was not closed. Attempting to close now.")
                self.stream.abort() # Abort immediately
                self.stream.close()
                self.stream = None

            print(f"DEBUG: Starting sounddevice stream. Samplerate: {SAMPLE_RATE}, Channels: {self.stream_channels}, Blocksize: {block_size}")
            self.stream = sd.OutputStream(
                samplerate=SAMPLE_RATE,
                blocksize=block_size,
                channels=self.stream_channels, # Always stereo for simplicity. Mono sources will be duplicated.
                dtype='float32',      # We generate float32 samples.
                callback=self._audio_callback
            )
            self.stream.start() # This starts the callback mechanism in its own thread.
            print("DEBUG: Sounddevice stream started.")
            if root and hasattr(root, "update_status_display"): root.update_status_display()

        except Exception as e:
            print(f"Error starting Sounddevice stream: {e}")
            if root and hasattr(root, "update_status_display"):
                root.update_status_display(error_message=f"Audio stream error: {e}")
            self.playing = False
            if self.stream: # If stream object was created but start failed
                try: self.stream.close()
                except: pass
            self.stream = None


    def stop(self):
        # "Make it stop! (the SoundDevice stream)"
        print("DEBUG: Stop action called.")
        self.stop_flag = True # Signal the callback to stop generating data and raise CallbackStop.

        if self.stream:
            print("DEBUG: Stream found, attempting to stop and close.")
            try:
                # The callback, upon seeing stop_flag, should raise sd.CallbackStop,
                # which will lead to the stream stopping.
                # We wait a bit for this to happen. If not, force stop/close.
                # A more robust way is to rely on sd.CallbackStop or use stream.abort()
                # Forcing stop() and close() here is generally safe.
                self.stream.stop()  # Stops invoking the callback
                self.stream.close() # Releases audio resources
                print("DEBUG: Sounddevice stream stopped and closed.")
            except Exception as e:
                print(f"Error stopping/closing Sounddevice stream: {e}")
            self.stream = None
        else:
            print("DEBUG: No active stream found to stop.")

        self.playing = False
        # Resetting current_time_offset here ensures that if play is hit again for a fixed tone,
        # it starts from phase 0. This is now handled by _initialize_X_states on start if needed.
        # self.current_time_offset = 0.0
        if root and hasattr(root, "update_status_display"): root.update_status_display()

    def set_frequency(self, freq_str_or_float):
        try:
            new_freq = float(freq_str_or_float)
            if self.frequency != new_freq:
                self.frequency = new_freq
                if self.waveform not in ["white_noise", "pink_noise", "brown_noise", "frequency_sweep"]:
                    # self.needs_settings_update = True # Not strictly needed if generate_audio_buffer reads self.frequency directly
                    pass # The next buffer generated will use the new frequency.
        except ValueError:
            print(f"Invalid frequency value: {freq_str_or_float}")


    def set_beat_frequency(self, beat_freq_str_or_float):
        try:
            new_beat_freq = float(beat_freq_str_or_float)
            if self.beat_frequency != new_beat_freq:
                self.beat_frequency = new_beat_freq
                if self.waveform == "binaural_beat":
                    # self.needs_settings_update = True
                    pass
        except ValueError:
             print(f"Invalid beat frequency value: {beat_freq_str_or_float}")

    def toggle_phase(self):
        self.phase_shift = not self.phase_shift
        # This change is picked up by generate_audio_buffer directly. No state re-init needed.
        if root and hasattr(root, "update_status_display"): root.update_status_display()


    def set_volume(self, vol_str_or_float):
        try:
            new_vol = float(vol_str_or_float)
            new_vol = max(0.0, min(1.0, new_vol)) # Clamp
            if self.volume != new_vol:
                self.volume = new_vol
                # The change will be applied in the next call to generate_audio_buffer.
                if root and hasattr(root, 'update_status_display'):
                    root.update_status_display()
        except ValueError:
            print(f"Invalid volume value: {vol_str_or_float}")

    def set_waveform(self, wf_name):
        if self.waveform != wf_name:
            previous_waveform_was_sweep = (self.waveform == "frequency_sweep")
            self.waveform = wf_name

            # Always reset general states like current_time_offset (done by _initialize_noise_states)
            self._initialize_noise_states()

            if wf_name == "frequency_sweep":
                self._initialize_sweep_state()

            # If changing away from sweep, or to sweep, a full re-evaluation of settings is good.
            self.needs_settings_update = True

            if root and hasattr(root, "toggle_binaural_controls_active_state"):
                root.toggle_binaural_controls_active_state()

# --- GUI Setup ---
# Now we start building the house. But first, let's see if we have an engine to put in it.
player = None # We start with an empty spot for our sound-making brain.

if SOUNDDEVICE_AVAILABLE:
    # Hooray! The sound libraries loaded! We have an engine!
    # Let's create a shiny new ToneGenerator and slot it into our 'player' variable.
    player = ToneGenerator()
else:
    # Aww, the engine fell out. Or was never delivered. The 'player' slot remains empty.
    # The error message was already printed to the console during our failed import attempt.
    # The GUI will see that 'player' is still None and will basically be a ghost town of disabled buttons.
    pass

# Here's the canvas for our masterpiece. Or, you know, our window.
root = tk.Tk()
root.title("Leona's Tinnitus Sound Generator (SoundDevice Edition)")

# --- Global Tkinter Variables for Timer & Sweep (largely unchanged) ---
# These are the magic strings and invisible wires that connect our GUI widgets (sliders, checkboxes)
# to our code's brain. When a slider moves, its variable changes, and vice-versa.
timer_enabled_var = tk.BooleanVar(value=False)
timer_duration_minutes_var = tk.IntVar(value=10)
timer_id_var = None # This will hold the ID of our "stop in X minutes" timer, so we can cancel it if needed.

# Let's figure out the initial positions for all the 'whoop whoop' machine's dials.
# We try to be smart and get the defaults from the player object we just created...
# but if the player doesn't exist (because the audio system is a potato), we'll just pull some reasonable numbers out of a hat.
_initial_sweep_start_freq = player.sweep_start_freq if player else 200.0
_initial_sweep_end_freq = player.sweep_end_freq if player else 800.0
_initial_sweep_duration = player.sweep_duration_one_way if player else 5.0
_initial_swept_waveform = player.swept_waveform if player else "sine"

# Now, create the actual Tkinter variables that will be wired up to the sweep setting widgets.
sweep_start_freq_var = tk.DoubleVar(value=_initial_sweep_start_freq)
sweep_end_freq_var = tk.DoubleVar(value=_initial_sweep_end_freq)
sweep_duration_var = tk.DoubleVar(value=_initial_sweep_duration)
SWEEP_WAVEFORMS = ["sine", "square", "sawtooth", "triangle"] # The official list of approved whoop shapes.
swept_waveform_var = tk.StringVar(value=_initial_swept_waveform)


# --- GUI Helper Functions (These are the strings that make the puppets dance) ---

def update_settings_and_status_display(event=None):
    # Welcome to Grand Central Station. Almost every user action comes through here.
    # This function's job is to read all the dials, tell the player, and then update the display to reflect reality.
    if not player:
        # First rule of Grand Central: if there's no train engine, you can't dispatch a train.
        # Just update the status to say everything is broken.
        if hasattr(root, 'update_status_display'): root.update_status_display(error_message="Audio system error (player not init).")
        return

    # --- Part 1: The Command Phase ---
    # Read all the current values from the GUI's magic variables and shove them into the player object.
    player.set_frequency(freq_var.get())
    player.set_beat_frequency(beat_freq_var.get())
    player.set_volume(volume_var.get())

    selected_waveform = waveform_var.get() # Get selected waveform first
    # This order is important! Set the waveform *before* the sweep parameters,
    # because `set_waveform` is like a mini-reset and might wipe out the sweep settings we're about to set.
    player.set_waveform(selected_waveform)

    # If the user has selected the majestic Frequency Sweep, we need to tell the player all about it.
    if selected_waveform == "frequency_sweep":
        player.set_sweep_params(
            sweep_start_freq_var.get(),
            sweep_end_freq_var.get(),
            sweep_duration_var.get(),
            swept_waveform_var.get()
        )

    # --- Part 2: The Feedback Phase ---
    # Now, we read the values *back* from the player. Why? Because the player might have clamped them
    # (e.g., user typed "99999" for volume, player clamped it to 1.0). This keeps the GUI honest.
    current_freq_label.config(text=f"Carrier Freq: {player.frequency:.0f} Hz")
    if str(int(player.frequency)) != freq_entry_var.get():
        freq_entry_var.set(str(int(player.frequency))) # Correct the text box if it's out of sync.

    beat_freq_display_label.config(text=f"Beat Freq: {player.beat_frequency:.1f} Hz")
    player_beat_freq_str = f"{player.beat_frequency:.1f}"
    # This looks complicated, but it just prevents a feedback loop while making sure the text box is correct.
    if beat_freq_entry_var.get() != player_beat_freq_str:
        try:
            if float(beat_freq_entry_var.get()) != player.beat_frequency:
                 beat_freq_entry_var.set(player_beat_freq_str)
        except ValueError: # User typed "banana". Just set it back to the last good value.
             beat_freq_entry_var.set(player_beat_freq_str)

    volume_display_label.config(text=f"Volume: {int(player.volume*100)}%")

    # We should probably also update the labels for the sweep settings, shouldn't we?
    if player: # Should always be true if we got this far, but hope is not a strategy.
        if 'sweep_start_display_label' in globals() and sweep_start_display_label:
             sweep_start_display_label.config(text=f"Start: {player.sweep_start_freq:.0f} Hz")
        if 'sweep_end_display_label' in globals() and sweep_end_display_label:
             sweep_end_display_label.config(text=f"End: {player.sweep_end_freq:.0f} Hz")
        if 'sweep_duration_display_label' in globals() and sweep_duration_display_label:
             sweep_duration_display_label.config(text=f"Time (1-way): {player.sweep_duration_one_way:.1f} s")
        if 'swept_waveform_display_label' in globals() and swept_waveform_display_label:
             swept_waveform_display_label.config(text=f"Shape: {player.swept_waveform}")

    # --- Part 3: The Finale ---
    # After all that, tell the main status bar at the bottom to refresh itself with all this new info.
    if hasattr(root, 'update_status_display'): root.update_status_display()


def root_update_status_display_impl(error_message=None):
    # This function is the Town Crier of our application. Its only job is to figure out
    # what's happening and shout it out in the big status label at the bottom of the window.
    status_text = ""
    # The order of these checks is a sad story, from total failure to glorious success.
    if not SOUNDDEVICE_AVAILABLE: # First, the most important question: is the entire audio system a lost cause?
        status_text = f"Status: ERROR - Audio system (Sounddevice) not available. {SD_ERROR_MESSAGE}"
    elif not player: # A strange but possible tragedy: the system is okay, but our player object failed to be born.
         status_text = "Status: ERROR - Audio player object not created."
    elif error_message: # Did another part of the code send us a specific complaint? If so, just display it.
        status_text = f"Status: ERROR - {error_message}"
    elif player.playing:
        # The happy path! We're making noise! Let's build a detailed string describing the racket.
        if player.waveform == "frequency_sweep":
            status_text = (f"Playing: Sweep {player.swept_waveform.capitalize()} "
                           f"({player.sweep_start_freq:.0f}-{player.sweep_end_freq:.0f}Hz over "
                           f"{player.sweep_duration_one_way:.1f}s each way). "
                           f"Currently at ~{player.sweep_current_freq_actual:.0f}Hz. "
                           f"Vol {player.volume*100:.0f}%")
            if player.phase_shift: status_text += ", Phase: ON"
        elif player.waveform == "binaural_beat":
            status_text = f"Playing: Vol {player.volume*100:.0f}% | {player.waveform}"
            status_text += f" ({player.frequency:.0f}Hz + {player.beat_frequency:.1f}Hz beat)"
        elif player.waveform not in ["white_noise", "pink_noise", "brown_noise"]: # For our standard, well-behaved tones...
            status_text = f"Playing: Vol {player.volume*100:.0f}% | {player.waveform}"
            status_text += f" ({player.frequency:.0f}Hz)"
            if player.phase_shift: status_text += f", Phase: ON"
        else: # For the unruly noises...
            status_text = f"Playing: Vol {player.volume*100:.0f}% | {player.waveform}"

        # If the timer is also running, we should probably mention that.
        if timer_enabled_var.get() and player.playing:
            status_text += f" | Timer: ON ({timer_duration_minutes_var.get()} min)"
    else:
        # If we're not playing, we're stopped. Simple as that.
        status_text = "Status: Stopped"
        # A weird edge case: what if the user stopped playback but the timer is still technically 'on'? Let's mention it.
        if timer_enabled_var.get() and timer_id_var:
            status_text += " (Timer active but playback stopped)"

    # And now, deliver the message to the label widget itself. Our Town Crier has spoken.
    status_label.config(text=status_text)
# And now for a bit of python magic. We attach our newly defined function directly to the root window object itself.
# This makes it super easy to call from anywhere, like a global emergency broadcast button or a hotline to the main office.
root.update_status_display = root_update_status_display_impl

def toggle_binaural_controls_active_state_impl():
    # This function is the GUI's bouncer. The fun police. The traffic cop.
    # Its job is to look at the current situation and mercilessly disable any controls
    # that don't make sense, preventing the user from trying to do something silly.

    # First, we gather our intelligence. What's the state of the world?
    is_binaural = (waveform_var.get() == "binaural_beat")
    is_noise = waveform_var.get() in ["white_noise", "pink_noise", "brown_noise"]
    is_sweep = (waveform_var.get() == "frequency_sweep")
    # The most important question: is the audio system even turned on?
    audio_ok = SOUNDDEVICE_AVAILABLE and player is not None

    # This is our default state. If audio is okay, things are clickable. If not, they're dead.
    global_state = tk.NORMAL if audio_ok else tk.DISABLED

    # Now for the specific rules. You can't enter the binaural club unless you're on the binaural list.
    binaural_state = tk.NORMAL if is_binaural and audio_ok else tk.DISABLED
    beat_freq_slider.config(state=binaural_state)
    beat_freq_entry.config(state=binaural_state)
    beat_freq_label_text.config(state=binaural_state if is_binaural and audio_ok else global_state)
    beat_freq_display_label.config(state=binaural_state)

    # You can't set a single frequency if you're making noise (which has all frequencies)
    # or sweeping (which has a constantly changing frequency). The bouncer says no.
    tone_freq_state = tk.NORMAL if not is_noise and not is_sweep and audio_ok else tk.DISABLED
    freq_slider.config(state=tone_freq_state)
    freq_entry.config(state=tone_freq_state)
    current_freq_label.config(state=tone_freq_state if not is_noise and not is_sweep and audio_ok else global_state)

    # Phase shifting noise or binaural beats is nonsensical. You can't invert chaos, it's still chaos.
    phase_button_state = tk.NORMAL if not is_noise and not is_binaural and audio_ok else tk.DISABLED
    phase_button.config(state=phase_button_state)

    # The sweep settings are a VIP section. Only accessible if you've selected "frequency_sweep".
    sweep_controls_state = tk.NORMAL if is_sweep and audio_ok else tk.DISABLED
    if 'sweep_start_freq_entry' in globals(): # A quick check to make sure the widgets actually exist before we poke them.
        sweep_start_freq_entry.config(state=sweep_controls_state)
        sweep_end_freq_entry.config(state=sweep_controls_state)
        sweep_duration_entry_widget.config(state=sweep_controls_state)
        swept_waveform_menu.config(state=sweep_controls_state)
        # The labels should also be greyed out, so it doesn't look like they apply.
        for label in [sweep_start_display_label, sweep_end_display_label, sweep_duration_display_label, swept_waveform_display_label]:
            if label: label.config(state=sweep_controls_state if is_sweep and audio_ok else global_state)
        # Let's even change the title of the frame to make it obvious.
        sweep_settings_frame.config(text="Frequency Sweep Settings" + (" (Active)" if is_sweep and audio_ok else ""))

    # And here's the scorched-earth policy. If the audio system is down, just disable everything.
    # No point in letting the user fiddle with dials that are connected to nothing.
    if not audio_ok:
        for widget in [freq_slider, freq_entry, beat_freq_slider, beat_freq_entry,
                       volume_slider, play_button, phase_button, waveform_menu]: # Yes, even the waveform menu.
            if widget: widget.config(state=tk.DISABLED)
        if 'sweep_start_freq_entry' in globals(): # Sweep controls too. Nuke 'em all.
             sweep_start_freq_entry.config(state=tk.DISABLED)
             sweep_end_freq_entry.config(state=tk.DISABLED)
             sweep_duration_entry_widget.config(state=tk.DISABLED)
             swept_waveform_menu.config(state=tk.DISABLED)
# And we attach our bouncer function to the root window for easy access. Another hotline!
root.toggle_binaural_controls_active_state = toggle_binaural_controls_active_state_impl

def on_freq_entry_change(event=None, var_to_set=None, entry_var=None, min_val=0, max_val=20000, is_float=False):
    # This trusty old workhorse handles the user typing numbers into the little text boxes.
    # It's a patient validator, prepared for the user to type "potato" at any moment.
    if not player: return # If there's no player, there's no point.
    try:
        # Step 1: Try to understand what the user typed. Is it even a number?
        val_str = entry_var.get()
        val = float(val_str) if is_float else int(val_str)
        # Step 2: Okay, it's a number. Is it a *reasonable* number?
        if min_val <= val <= max_val:
            # Step 3: Success! It's a valid number. Update the linked variable (which moves the slider) and refresh everything.
            var_to_set.set(val)
            update_settings_and_status_display()
        else:
            # It's a number, but it's out of bounds. Gently guide the user back by reverting the text box.
            current_val = var_to_set.get()
            entry_var.set(f"{current_val:.1f}" if is_float else str(int(current_val)))
    except ValueError:
        # Aaaand they typed "potato". Revert the text box to the last known good value. Tsk tsk.
        current_val = var_to_set.get()
        entry_var.set(f"{current_val:.1f}" if is_float else str(int(current_val)))

def play_action():
    # This is it. The big one. The function that runs when the user presses the "Play" button.
    global timer_id_var
    # First, some safety checks. Do we even have a player? Is the audio system working?
    # If not, show an angry popup and refuse to do anything.
    if not player:
        messagebox.showerror("Audio Error", "Audio system not available or player not initialized.")
        return
    if not SOUNDDEVICE_AVAILABLE: # An extra explicit check, because we're paranoid.
        messagebox.showerror("Audio Error", f"Sounddevice audio system not available.\n{SD_ERROR_MESSAGE}")
        return

    # Okay, we're cleared for takeoff. First, make sure the player has the latest settings from the GUI.
    update_settings_and_status_display()
    # Now, tell the player to start its engine. This is what actually starts the sounddevice stream.
    player.start()

    # Now, let's deal with that pesky timer.
    if timer_id_var: # If a timer was already set, cancel it. We're starting fresh.
        root.after_cancel(timer_id_var)
        timer_id_var = None
    if timer_enabled_var.get(): # If the user wants a timer...
        duration_ms = timer_duration_minutes_var.get() * 60 * 1000
        if duration_ms > 0:
            # ...schedule the `stop_action_for_timer` function to run in the future.
            timer_id_var = root.after(duration_ms, stop_action_for_timer)

    # Finally, let's be explicit and make sure the "Now Playing" sign is lit up.
    if hasattr(root, "update_status_display"): root.update_status_display()


def stop_action_for_timer():
    # This isn't called by a button. This is the ghost in the machine that pulls the plug when the timer runs out.
    global timer_id_var
    if player: player.stop() # Tell the player to stop the noise.
    timer_id_var = None # The timer has served its purpose.
    root.update_status_display() # Update the status to "Stopped".
    messagebox.showinfo("Playback Timer", "Playback finished due to timer.") # Let the user know why it stopped.

def stop_action():
    # The big red panic button. The emergency brake. This is for when the user wants it to stop NOW.
    global timer_id_var
    if player: player.stop() # Tell the player to cease and desist.
    if timer_id_var: # If there was a timer running...
        root.after_cancel(timer_id_var) # ...disarm it.
        timer_id_var = None
    root.update_status_display() # Update the status immediately.

def toggle_phase_action():
    # This runs when the user clicks the "Phase Shift" button.
    if not player: return # Can't shift what doesn't exist.
    # Check if this even makes sense for the current waveform.
    if player.waveform not in ["white_noise", "pink_noise", "brown_noise", "binaural_beat"]:
        player.toggle_phase() # Tell the player to flip its bits.
        # Update the button's own text so the user knows what they did.
        phase_button.config(text=f"Phase Shift: {'ON' if player.phase_shift else 'OFF'}")
        root.update_status_display() # And update the main status bar.

# --- Presets Functions ---
# For when you finally create the perfect 'annoying hum' and want to remember how you did it later.
# The beauty of these is they didn't really need to change. They just save/load the player's high-level settings,
# and don't care about the greasy inner workings of the audio engine. A rare win for good design!

def save_preset():
    # This is for bottling lightning. Or at least, bottling the settings for a specific sine wave.
    if not player:
        # A quick sanity check. Can't save the settings of a player that doesn't exist. That's just philosophy.
        messagebox.showerror("Error", "Cannot save preset, audio player not ready.")
        return

    # Pop open a dialog and ask the user, "Where, precisely, do you want to entomb this particular set of configurations?"
    filepath = filedialog.asksaveasfilename(
        defaultextension=".json",
        filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        title="Save Preset As"
    )
    # If the user gets spooked and hits 'Cancel', we just nod and back away slowly. No file, no problem.
    if not filepath: return

    # Gather up all the current settings like a squirrel preparing for winter.
    # We grab everything from the player's brain and the GUI's state.
    settings = {
        "frequency": player.frequency, "beat_frequency": player.beat_frequency,
        "volume": player.volume, "waveform": player.waveform, "phase_shift": player.phase_shift,
        "sweep_start_freq": player.sweep_start_freq, "sweep_end_freq": player.sweep_end_freq,
        "sweep_duration_one_way": player.sweep_duration_one_way, "swept_waveform": player.swept_waveform,
        "timer_enabled": timer_enabled_var.get(), "timer_duration_minutes": timer_duration_minutes_var.get()
    }

    try:
        # Now, use the magic of JSON to etch this dictionary into a file. `indent=4` makes it human-readable, which is nice.
        with open(filepath, 'w') as f: json.dump(settings, f, indent=4)
        # Let the user know their precious settings are safe.
        messagebox.showinfo("Preset Saved", f"Preset saved to {filepath}.")
    except Exception as e:
        # Something went wrong. The disk is full, permissions are wrong, the cat unplugged the computer... who knows.
        messagebox.showerror("Error Saving Preset", f"Could not save preset: {e}.")

def load_preset():
    # The reverse of bottling lightning: reanimating a saved configuration from its slumber.
    if not player:
        # Again, can't load a preset if there's no machine to load it into.
        messagebox.showerror("Error", "Cannot load preset, audio player not ready.")
        return

    # Ask the user, "Which of your ancient scrolls do you wish to read?"
    filepath = filedialog.askopenfilename(
        defaultextension=".json", filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        title="Load Preset"
    )
    # User changed their mind. That's fine. We're not pushy.
    if not filepath: return

    try:
        # Open the file and let the JSON wizard decipher its contents into our `settings` dictionary.
        with open(filepath, 'r') as f: settings = json.load(f)

        # Now for the delicate part. We painstakingly update all our GUI variables from the loaded settings.
        # We use `.get()` with a default value as a brilliant defense mechanism. This way, if we load an old
        # preset that's missing a new setting, the app doesn't just explode. It uses a sensible default instead.
        freq_var.set(settings.get("frequency", 440.0))
        beat_freq_var.set(settings.get("beat_frequency", 4.0))
        volume_var.set(settings.get("volume", 0.8))
        waveform_var.set(settings.get("waveform", "sine"))
        player.phase_shift = settings.get("phase_shift", False) # This one goes directly to the player.
        phase_button.config(text=f"Phase Shift: {'ON' if player.phase_shift else 'OFF'}") # And we update its button text.
        sweep_start_freq_var.set(settings.get("sweep_start_freq", _initial_sweep_start_freq))
        sweep_end_freq_var.set(settings.get("sweep_end_freq", _initial_sweep_end_freq))
        sweep_duration_var.set(settings.get("sweep_duration_one_way", _initial_sweep_duration))
        swept_waveform_var.set(settings.get("swept_waveform", _initial_swept_waveform))
        timer_enabled_var.set(settings.get("timer_enabled", False))
        timer_duration_minutes_var.set(settings.get("timer_duration_minutes", 10))

        # After force-feeding all the new settings into the GUI, we call the master update function
        # to make sure the player, labels, and everything else is on the same page.
        update_settings_and_status_display()
        messagebox.showinfo("Preset Loaded", f"Preset loaded from {filepath}.")
    except Exception as e:
        # The file was corrupt, wasn't JSON, or was just generally offensive to the computer.
        messagebox.showerror("Error Loading Preset", f"Could not load preset: {e}.")


# --- Main Window Layout (GUI construction - largely unchanged) ---
# Time to build the house. This is where we lay out all the buttons and dials, piece by painful piece.
# It's like Lego, but with more parentheses and a vague sense of existential dread.

# Presets Frame: The "Save your work, you fool!" section.
preset_frame = ttk.Frame(root); preset_frame.pack(pady=5, fill="x", padx=5)
ttk.Button(preset_frame, text="Save Preset", command=save_preset).pack(side=tk.LEFT, padx=10)
ttk.Button(preset_frame, text="Load Preset", command=load_preset).pack(side=tk.LEFT, padx=10)

# Tone Settings Frame: The main control panel for our standard, well-behaved tones.
# Grab the default frequency from the player, but if the player is a ghost, just pick a number. 440 is a good number.
_initial_freq = player.frequency if player else 440.0
_initial_beat_freq = player.beat_frequency if player else 4.0
freq_main_frame = ttk.LabelFrame(root, text="Tone Settings (Not for Sweep)")
freq_main_frame.pack(pady=5, padx=5, fill="x")
# A sub-frame for the frequency slider and entry box, to keep them cozy.
freq_frame = ttk.Frame(freq_main_frame); freq_frame.pack(pady=2, fill="x", expand=True)
ttk.Label(freq_frame, text="Carrier Freq (Hz):").pack(side=tk.LEFT, padx=5)
freq_var = tk.DoubleVar(value=_initial_freq) # The magic variable for frequency.
freq_slider = ttk.Scale(freq_frame, from_=20, to=15000, variable=freq_var, orient="horizontal", length=180, command=update_settings_and_status_display)
freq_slider.pack(side=tk.LEFT, padx=5, fill="x", expand=True)
freq_entry_var = tk.StringVar(value=str(int(_initial_freq))) # A separate variable for the text box.
freq_entry = ttk.Entry(freq_frame, textvariable=freq_entry_var, width=7)
freq_entry.pack(side=tk.LEFT, padx=5)
# This is the wiring. "When the user hits Enter or clicks away from this box, call our validation function."
freq_entry.bind("<Return>", lambda e: on_freq_entry_change(e, freq_var, freq_entry_var, 20, 15000))
freq_entry.bind("<FocusOut>", lambda e: on_freq_entry_change(e, freq_var, freq_entry_var, 20, 15000))
current_freq_label = ttk.Label(freq_main_frame, text=f"Carrier Freq: {_initial_freq:.0f} Hz")
current_freq_label.pack(pady=2)
# And another sub-frame for the binaural beat controls.
beat_freq_frame = ttk.Frame(freq_main_frame); beat_freq_frame.pack(pady=2, fill="x", expand=True)
beat_freq_label_text = ttk.Label(beat_freq_frame, text="Beat Freq (Hz):"); beat_freq_label_text.pack(side=tk.LEFT, padx=5)
beat_freq_var = tk.DoubleVar(value=_initial_beat_freq)
beat_freq_slider = ttk.Scale(beat_freq_frame, from_=0.1, to=30.0, variable=beat_freq_var, orient="horizontal", length=180, command=update_settings_and_status_display)
beat_freq_slider.pack(side=tk.LEFT, padx=5, fill="x", expand=True)
beat_freq_entry_var = tk.StringVar(value=f"{_initial_beat_freq:.1f}")
beat_freq_entry = ttk.Entry(beat_freq_frame, textvariable=beat_freq_entry_var, width=7)
beat_freq_entry.pack(side=tk.LEFT, padx=5)
beat_freq_entry.bind("<Return>", lambda e: on_freq_entry_change(e, beat_freq_var, beat_freq_entry_var, 0.1, 30.0, is_float=True))
beat_freq_entry.bind("<FocusOut>", lambda e: on_freq_entry_change(e, beat_freq_var, beat_freq_entry_var, 0.1, 30.0, is_float=True))
beat_freq_display_label = ttk.Label(freq_main_frame, text=f"Beat Freq: {_initial_beat_freq:.1f} Hz")
beat_freq_display_label.pack(pady=2)

# Waveform Selection Frame: The "Choose Your Fighter" dropdown menu.
_initial_waveform = player.waveform if player else "sine"
waveform_frame = ttk.LabelFrame(root, text="Sound Type"); waveform_frame.pack(pady=5, padx=5, fill="x")
ttk.Label(waveform_frame, text="Waveform:").pack(side=tk.LEFT, padx=5)
waveforms = ["sine", "square", "sawtooth", "triangle", "white_noise", "pink_noise", "brown_noise", "binaural_beat", "frequency_sweep"]
waveform_var = tk.StringVar(value=_initial_waveform)
waveform_menu = ttk.Combobox(waveform_frame, textvariable=waveform_var, values=waveforms, state="readonly", width=15)
waveform_menu.pack(side=tk.LEFT, padx=5, pady=5)
# When a new waveform is selected, we have to do two things: update the settings AND toggle which controls are active.
waveform_menu.bind("<<ComboboxSelected>>", lambda e: (update_settings_and_status_display(), root.toggle_binaural_controls_active_state()))

# Frequency Sweep Settings Frame: The "Mad Scientist's Corner" for controlling the whoop-whoop machine.
sweep_settings_frame = ttk.LabelFrame(root, text="Frequency Sweep Settings"); sweep_settings_frame.pack(pady=5, padx=5, fill="x")
# A little frame for the Start Frequency controls...
sweep_sf_frame = ttk.Frame(sweep_settings_frame); sweep_sf_frame.pack(fill="x", padx=2, pady=2)
ttk.Label(sweep_sf_frame, text="Start Freq (Hz):").pack(side=tk.LEFT, padx=5)
sweep_start_freq_entry = ttk.Entry(sweep_sf_frame, textvariable=sweep_start_freq_var, width=7)
sweep_start_freq_entry.pack(side=tk.LEFT, padx=5)
sweep_start_freq_entry.bind("<Return>", update_settings_and_status_display) # Any change here should trigger a full update.
sweep_start_freq_entry.bind("<FocusOut>", update_settings_and_status_display)
sweep_start_display_label = ttk.Label(sweep_sf_frame, text=f"Start: {_initial_sweep_start_freq:.0f} Hz")
sweep_start_display_label.pack(side=tk.LEFT, padx=5)
# And one for the End Frequency...
sweep_ef_frame = ttk.Frame(sweep_settings_frame); sweep_ef_frame.pack(fill="x", padx=2, pady=2)
ttk.Label(sweep_ef_frame, text="End Freq (Hz):").pack(side=tk.LEFT, padx=5)
sweep_end_freq_entry = ttk.Entry(sweep_ef_frame, textvariable=sweep_end_freq_var, width=7)
sweep_end_freq_entry.pack(side=tk.LEFT, padx=5)
sweep_end_freq_entry.bind("<Return>", update_settings_and_status_display)
sweep_end_freq_entry.bind("<FocusOut>", update_settings_and_status_display)
sweep_end_display_label = ttk.Label(sweep_ef_frame, text=f"End: {_initial_sweep_end_freq:.0f} Hz")
sweep_end_display_label.pack(side=tk.LEFT, padx=5)
# And for the Duration...
sweep_dur_frame = ttk.Frame(sweep_settings_frame); sweep_dur_frame.pack(fill="x", padx=2, pady=2)
ttk.Label(sweep_dur_frame, text="Duration (s, 1-way):").pack(side=tk.LEFT, padx=5)
sweep_duration_entry_widget = ttk.Entry(sweep_dur_frame, textvariable=sweep_duration_var, width=7)
sweep_duration_entry_widget.pack(side=tk.LEFT, padx=5)
sweep_duration_entry_widget.bind("<Return>", update_settings_and_status_display)
sweep_duration_entry_widget.bind("<FocusOut>", update_settings_and_status_display)
sweep_duration_display_label = ttk.Label(sweep_dur_frame, text=f"Time: {_initial_sweep_duration:.1f} s")
sweep_duration_display_label.pack(side=tk.LEFT, padx=5)
# And finally, for the shape of the sweep itself.
sweep_shape_frame = ttk.Frame(sweep_settings_frame); sweep_shape_frame.pack(fill="x", padx=2, pady=2)
ttk.Label(sweep_shape_frame, text="Sweep Shape:").pack(side=tk.LEFT, padx=5)
swept_waveform_menu = ttk.Combobox(sweep_shape_frame, textvariable=swept_waveform_var, values=SWEEP_WAVEFORMS, state="readonly", width=12)
swept_waveform_menu.pack(side=tk.LEFT, padx=5)
swept_waveform_menu.bind("<<ComboboxSelected>>", update_settings_and_status_display)
swept_waveform_display_label = ttk.Label(sweep_shape_frame, text=f"Shape: {_initial_swept_waveform}")
swept_waveform_display_label.pack(side=tk.LEFT, padx=5)

# --- Volume Control Frame ---
# The most important knob in the entire application: the 'Loudness' control.
# This one goes from "is this thing on?" to "my ears are ringing and the dog is hiding."
_initial_volume = player.volume if player else 0.8 # Get the starting volume, or just pick 0.8 which is loud but not *too* loud.
volume_frame = ttk.LabelFrame(root, text="Output Level"); volume_frame.pack(pady=5, padx=5, fill="x")
ttk.Label(volume_frame, text="Volume:").pack(side=tk.LEFT, padx=5)
volume_var = tk.DoubleVar(value=_initial_volume) # The magic variable for the volume slider.
# A slider from 0.0 (blissful silence) to 1.0 (maximum tinnitus).
volume_slider = ttk.Scale(volume_frame, from_=0.0, to=1.0, variable=volume_var, orient="horizontal", length=150, command=update_settings_and_status_display)
volume_slider.pack(side=tk.LEFT, padx=5, fill="x", expand=True)
# A little percentage display so the user feels like they have precise, scientific control over the loudness.
volume_display_label = ttk.Label(volume_frame, text=f"Volume: {int(_initial_volume*100)}%")
volume_display_label.pack(side=tk.LEFT, padx=5)

# --- Phase Shift Button ---
# The button for the true audio nerds, the phase inverter. It flips the wave upside down.
# Most people won't touch it, but the ones who know, *know*.
initial_phase_text = "OFF"
# We need to check the player's initial state so the button text is correct on launch.
if player and player.phase_shift: initial_phase_text = "ON"
# And now we create the button itself, a lonely widget out in the open.
phase_button = ttk.Button(root, text=f"Phase Shift: {initial_phase_text}", command=toggle_phase_action)
phase_button.pack(pady=5)

# --- Timer Controls Frame ---
# The "I want to fall asleep to this but not leave it running all night" control panel. A feature for the responsible droner.
timer_frame = ttk.LabelFrame(root, text="Playback Timer"); timer_frame.pack(pady=5, padx=5, fill="x")
# The on/off switch for the timer. We hook its command to the status display so the user gets immediate feedback.
timer_enable_checkbox = ttk.Checkbutton(timer_frame, text="Enable Timer", variable=timer_enabled_var, command=root.update_status_display)
timer_enable_checkbox.pack(side=tk.LEFT, padx=5)
ttk.Label(timer_frame, text="Duration (min):").pack(side=tk.LEFT, padx=5)
# A little box for them to type in how many minutes of auditory bliss (or torture) they want.
timer_duration_entry = ttk.Entry(timer_frame, textvariable=timer_duration_minutes_var, width=5)
timer_duration_entry.pack(side=tk.LEFT, padx=5)

# --- Play/Stop Buttons Frame ---
# The main event. The big "Go" button and its "Oh God, make it stop" friend.
controls_frame = ttk.Frame(root); controls_frame.pack(pady=10)
# A little bit of flair. We're creating a special style to make the Play button big, bold, and green.
# It's inviting! It practically begs to be clicked. Don't you want to see what happens?
s = ttk.Style(); s.configure('Accent.TButton', font=('Helvetica', 10, 'bold'), foreground='green')
play_button = ttk.Button(controls_frame, text="Play", command=play_action, style="Accent.TButton")
play_button.pack(side=tk.LEFT, padx=10)
# And the regular, unassuming Stop button.
ttk.Button(controls_frame, text="Stop", command=stop_action).pack(side=tk.LEFT, padx=10)

# --- Status Label ---
# The ticker tape at the bottom that tells the user what's happening, what's broken, or what they just did.
# `relief=tk.SUNKEN` makes it look a bit more official and slightly depressed.
status_label = ttk.Label(root, text="Status: Initializing...", relief=tk.SUNKEN, anchor=tk.W, padding=(5,5))
status_label.pack(pady=10, fill="x", expand=True, ipady=5)

# --- Closing Protocol ---
# This is the "shut down the nuclear reactor before abandoning the facility" protocol.
# Don't just slam the door on your way out! We need a graceful exit to avoid... consequences.
def on_closing():
    global timer_id_var
    # First, kill any pending timers so they don't try to run after the window is gone, like a headless chicken.
    if timer_id_var:
        try: root.after_cancel(timer_id_var)
        except tk.TclError: pass # It might already be gone. That's fine. Don't make a fuss.

    # THE MOST CRUCIAL PART. Tell the audio player to stop its stream.
    # If we don't do this, we get a ghost process playing sound forever until the user reboots. Ask me how I know.
    if player: player.stop()

    # Sounddevice streams should now be closed, so we don't need a global stop command.
    # sd.stop() # Global stop, not usually needed if streams are managed like the good little objects they are.

    # Now that everything is safe and quiet, we can finally demolish the window.
    root.destroy()

# This is the magic wire that connects our special "on_closing" function to the window's main 'X' button.
root.protocol("WM_DELETE_WINDOW", on_closing)

# --- Initial UI State Updates ---
# The last-minute primping and preening before the curtain goes up.
# After building all the widgets, we need to run our update functions once to set the correct initial state.
if player: # If the player was successfully born (i.e., SOUNDDEVICE_AVAILABLE was true)...
    # ...sync the GUI labels with the player's default state.
    update_settings_and_status_display()
# Run the bouncer function to disable any controls that shouldn't be active at the start.
root.toggle_binaural_controls_active_state()
# And set the initial message in the status bar. It'll either say 'Stopped' or 'Everything is on fire.'
root.update_status_display()

# And... action! This line starts the GUI event loop. From here on out, Tkinter is in charge. God help us all.
root.mainloop()

# --- Cleanup at the very end ---
# The show is over, the audience has gone home.
# Pygame cleanup is no longer needed. We are free from its shackles.
# Sounddevice streams were dutifully closed by player.stop() when the window was closed.
# No global sd.quit() is typically required. We were clean and tidy.
print("Application closed.")
# Good night my sweet SoundDevice-powered prince.
