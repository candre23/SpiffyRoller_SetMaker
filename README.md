# Spiffy Roller Set Maker

**Spiffy Roller Set Maker** is a desktop editor for creating custom dice sets for [Spiffy Roller](https://github.com/candre23/SpiffyRoller).

It provides a graphical interface for defining dice, faces, colors, symbols, custom artwork, and Lua-based roll rules, then exports the finished project as a Spiffy Roller-compatible `.set` file.

 <img width="1307" height="950" alt="setmaker" src="https://github.com/user-attachments/assets/5d203f49-fc96-4d88-9292-146de10bba69" />

## Features

- Create complete custom Spiffy Roller dice sets without manually editing JSON files
- Define multiple die types in a single set
- Built-in 48×48 face artwork editor
- Import existing images
- Convert imported artwork into 1-bit mask or 4-bit indexed-color
- Up to four editable artwork layers per face
- Per-layer image controls
- Manual pixel editing
- Real-size die-face preview
- Copy face artwork between faces
- Edit & validate rules.json and Lua roll-resolution scripts
- Import & export sets as folders or packaged .set files
- Save set project files that preserve layers and source images

## Installation

### Windows

Windows users do **not** need Python or any additional packages.

1. Open the **Releases** section of this repository.
2. Download the latest Spiffy Roller Set Maker `.exe`.
3. Run the executable.

The application is portable and does not require a traditional installer.

Windows may display a SmartScreen warning because the executable is not digitally signed. If you downloaded it from the official repository release, choose **More info** and then **Run anyway**.

### Running from Source

The Set Maker is written in Python and can also be run directly from source on systems with Python and Tk support.

Required Python packages:

```text
Pillow
```

Optional:

```text
luaparser
```

`luaparser` is only required for the **Validate rules.lua syntax** function.

A typical setup is:

```bash
python -m pip install pillow luaparser
python spiffy_roller_set_maker.py
```

Tkinter is included with standard Windows Python installations. Some Linux distributions package Tk separately.

## Basic Workflow

1. Start a new project.
2. Enter the dice-set name and ID.
3. Choose how many die types the set contains.
4. Configure each die.
5. Define the faces for each die.
6. Add labels, values, symbols, colors, or custom artwork as needed.
7. Configure the rules manifest and Lua roll-resolution script.
8. Save the editable project as an `.srs` file.
9. Export the finished set as a `.set` file.
10. Copy the `.set` file to Spiffy Roller.

For complete instructions, see [`manual.md`](manual.md).

For the full Spiffy Roller custom dice format specification, see [`custom_dice_template_guide.md`](custom_dice_template_guide.md).

## Compatibility

Spiffy Roller Set Maker creates sets for the current Spiffy Roller custom dice format.

Firmware project:

[https://github.com/candre23/SpiffyRoller](https://github.com/candre23/SpiffyRoller)

## Documentation

- [`manual.md`](manual.md) - complete Set Maker operating instructions
- [`custom_dice_template_guide.md`](custom_dice_template_guide.md) - complete Spiffy Roller `.set` format and Lua scripting reference

## AI & Safety Disclaimer

The code and documentation included in this project is primarily vibeslop. The human writing this sentence in particular can barely code and doesn't really understand how any of this works. It Works On My Machine and hasn't caused my genitals to explode, but your mileage may vary. I make absolutely no guarantee as to the safety or security of the contents of this project. Use at your own risk. Or don't.

## License

Spiffy Roller Set Maker is released into the public domain under The Unlicense.
