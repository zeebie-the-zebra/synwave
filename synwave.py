import tkinter as tk
from tkinter import ttk
import wave
import struct
import math
import threading
import time
import os
import pygame

SAMPLE_RATE = 44100
DURATION = 1  # seconds
WAV_FILE = "temp_tone.wav"

# Initialize pygame mixer
pygame.mixer.init(frequency=SAMPLE_RATE)

class ToneGenerator:
    def __init__(self):
        self.frequency = 440
        self.phase_shift = False
        self.playing = False
        self.thread = None
        self.stop_flag = False

    def generate_wave(self):
        with wave.open(WAV_FILE, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)  # 16-bit
            wf.setframerate(SAMPLE_RATE)

            for i in range(int(SAMPLE_RATE * DURATION)):
                angle = 2.0 * math.pi * self.frequency * i / SAMPLE_RATE
                if self.phase_shift:
                    angle += math.pi  # 180° phase shift

                value = int(32767.0 * math.sin(angle))
                data = struct.pack('<h', value)
                wf.writeframesraw(data)

    def audio_loop(self):
        while not self.stop_flag:
            self.generate_wave()
            sound = pygame.mixer.Sound(WAV_FILE)
            sound.play()  # Non-blocking
            time.sleep(DURATION)  # Sleep to match the duration of the tone
        if os.path.exists(WAV_FILE):
            os.remove(WAV_FILE)

    def start(self):
        if not self.playing:
            self.stop_flag = False
            self.playing = True
            self.thread = threading.Thread(target=self.audio_loop, daemon=True)
            self.thread.start()

    def stop(self):
        self.stop_flag = True
        self.playing = False

    def set_frequency(self, freq):
        self.frequency = freq

    def toggle_phase(self):
        self.phase_shift = not self.phase_shift


# GUI setup
player = ToneGenerator()
root = tk.Tk()
root.title("Tinnitus Tone Generator")

# Frequency Label
freq_label = ttk.Label(root, text="Frequency (Hz):")
freq_label.pack()

# Frequency Slider
freq_var = tk.IntVar(value=440)
freq_slider = ttk.Scale(root, from_=100, to=12000, variable=freq_var, orient="horizontal", length=300)
freq_slider.pack()

# Display the current frequency
current_freq_label = ttk.Label(root, text="Current Frequency: 440 Hz")
current_freq_label.pack()

def update_frequency_label(val):
    current_freq_label.config(text=f"Current Frequency: {int(val)} Hz")
    player.set_frequency(int(val))

freq_slider.bind("<Motion>", lambda event: update_frequency_label(freq_var.get()))

def toggle_phase():
    player.toggle_phase()
    phase_button.config(text=f"Phase Shift: {'ON' if player.phase_shift else 'OFF'}")

phase_button = ttk.Button(root, text="Phase Shift: OFF", command=toggle_phase)
phase_button.pack(pady=5)

def play():
    player.set_frequency(freq_var.get())
    player.start()

def stop():
    player.stop()

ttk.Button(root, text="Play", command=play).pack(pady=5)
ttk.Button(root, text="Stop", command=stop).pack(pady=5)

def on_closing():
    player.stop()
    root.destroy()

root.protocol("WM_DELETE_WINDOW", on_closing)
root.mainloop()
