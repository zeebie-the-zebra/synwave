# Leona's Tinnitus Sound Generator (SynWave.py)

Welcome to Leona's Tinnitus Sound Generator! This application allows you to generate various types of sound waves, including tones, noises, and binaural beats. It's designed with a simple graphical user interface for easy control over sound parameters. Maybe it'll help with that ringing, or maybe you just like making interesting noises. Either way, have fun!

---

## Disclaimer

**This application is intended for informational and personal use only and is not a medically tested or certified treatment for tinnitus or any other condition.**

The tone generator has not been evaluated by medical professionals, and no claims are made regarding its effectiveness for therapeutic purposes.

**Use at your own risk.** The author of this script assumes no responsibility or liability for any damage, discomfort, hearing issues, or adverse effects caused directly or indirectly by the use of this software.

If you suffer from tinnitus or any hearing condition, please consult a qualified healthcare provider before using this tool.

---

## Features

*   **Multiple Waveforms**: Generate Sine, Square, Sawtooth, and Triangle waves.
*   **Noise Generation**: Produce White, Pink, and Brown (Brownian/Red) noise.
*   **Binaural Beats**: Create binaural beats by specifying a carrier frequency and a beat frequency.
*   **Adjustable Frequencies**:
    *   Carrier Frequency: 20 Hz to 15000 Hz for tones.
    *   Beat Frequency: 0.1 Hz to 30.0 Hz for binaural beats.
*   **Volume Control**: Adjust the output volume from 0% to 100%.
*   **Phase Shift**: Toggle a 180-degree phase shift for tonal waveforms (Sine, Square, Sawtooth, Triangle).
*   **Playback Timer**: Set a timer (in minutes) to automatically stop playback.
*   **Preset System**:
    *   Save your current sound settings (waveform, frequencies, volume, phase, timer) to a JSON file.
    *   Load previously saved presets.
*   **Graphical User Interface (GUI)**: Easy-to-use interface built with Tkinter.
*   **Real-time Updates**: Most settings changes are applied immediately or on the next sound buffer.
*   **Status Display**: A handy status bar shows what's currently playing, volume levels, selected frequencies, and any timer information or error messages.

---

## Requirements

*   **Python 3.x**: The script is written for Python 3. (Tested with Python 3.7+).
*   **Pygame**: Used for audio generation and playback.
    *   You can install it via pip: `pip install pygame`
*   **Tkinter**: Used for the GUI. This is usually included with standard Python installations. If not, you may need to install it separately (e.g., `sudo apt-get install python3-tk` on Debian/Ubuntu).

---

## How to Use

### 1. Installation

1.  Make sure you have Python 3 installed on your system.
2.  Install the Pygame library if you haven't already: (In your Linux terminal / Windows cmd)
    ```bash
    pip install pygame
    ```
3.  Download or clone the `SynWave.py` script to your computer.

### 2. Running the Script

Open a terminal or command prompt, navigate to the directory where you saved `SynWave.py`, and run:

```bash
python SynWave.py

```

![Alt text](https://github.com/zeebie-the-zebra/synwave/blob/main/Screenshot_20250529_053226.png)


# Leona's Tinnitus Sound Generator (Synwave-SoundDevice-V1.py)
This version has replaced pygame with numpty and sounddevice libaries due to a bug I couldnt quash in pygame (generated tones between 9000~12000hz werent working correctly)

## Features
*   **Sweep**: You can now set a frequency range and sweep through it over X amount of seconds. 

## Requirements

*   **Python 3.x**: The script is written for Python 3. (Tested with Python 3.7+).
*   **Numpy & Sound Device**: Used for audio generation and playback.
    *   You can install it via pip: `pip install sounddevice numpy`
*   **Tkinter**: Used for the GUI. This is usually included with standard Python installations. If not, you may need to install it separately (e.g., `sudo apt-get install python3-tk` on Debian/Ubuntu).

## How to Use

### 1. Installation

1.  Make sure you have Python 3 installed on your system.
2.  Install the Sounddevice/Numpy library if you haven't already: (In your Linux terminal / Windows cmd)
    ```bash
    pip install sounddevice numpy
    ```
3.  Download or clone the `Synwave-SoundDevice-V1.py` script to your computer.

### 2. Running the Script

Open a terminal or command prompt, navigate to the directory where you saved `Synwave-SoundDevice-V1.py`, and run:

```bash
python Synwave-SoundDevice-V1.py

```
![Alt text](https://github.com/zeebie-the-zebra/synwave/blob/main/Screenshot_20250607_014047.png)
---
