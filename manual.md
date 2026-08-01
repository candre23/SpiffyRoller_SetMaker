# Spiffy Roller Set Maker Manual

This manual explains how to use **Spiffy Roller Set Maker** to create, edit, save, import, and export custom dice sets for Spiffy Roller.

For the actual `.set` file specification, supported JSON fields, Lua scripting interface, result objects, post-roll actions, and firmware-side format behavior, see:

[`custom_dice_template_guide.md`](custom_dice_template_guide.md)

---

# 1. Overview

Spiffy Roller Set Maker is a graphical editor for building custom Spiffy Roller dice sets.

The application lets you:

- Create one or more die types in a set
- Configure die shapes and colors
- Define every face individually
- Assign labels, numeric values, symbols, and color overrides
- Create 48×48 face artwork
- Import and process existing artwork
- Work with multiple artwork layers
- Edit the rules manifest and Lua roll script
- Save editable Set Maker projects
- Import existing Spiffy Roller sets
- Export completed `.set` files for use on the roller

The Set Maker uses two main file formats:

- `.srs` for editable Set Maker project files
- `.set` for finished Spiffy Roller dice sets

Keep the `.srs` file if you expect to edit a set again later.

---

# 2. Starting the Program

On Windows, launch the standalone Set Maker executable.

If running from Python source instead, launch:

```bash
python spiffy_roller_set_maker.py
```

The main window contains:

- A menu bar
- A **General** tab
- One tab for each die type in the current set

The window title also shows the application version and, when a project has been saved or opened, the current `.srs` filename.

---

# 3. File Menu

The **File** menu contains all project, import, and export functions.

## New set project

Creates a new blank Set Maker project.

The program asks before discarding the current project.

A new project starts with:

- One die type
- Six faces
- Default die colors
- A default Lua rules manifest
- A basic Lua script that totals numeric face values

## Open existing project

Opens a previously saved `.srs` project.

Use this when continuing work on a set created in the Set Maker.

An `.srs` project preserves editor-specific data such as:

- Imported source images
- Layer contents
- Artwork positioning
- Gamma
- Threshold
- Palette data
- Current die and face configuration
- Rules text
- Lua script

This is the preferred format for ongoing editing.

## Save project

Saves the current project to its existing `.srs` file.

If the project has not yet been saved, this behaves like **Save project as...**.

## Save project as...

Saves the current project to a new `.srs` file.

The default filename is based on the current Set ID.

## Import dice set folder

Imports an unpacked Spiffy Roller dice-set directory containing a `set.json`.

The Set Maker reads the set definition, rules files, dice, faces, and artwork that it can reconstruct.

Imported final sets do not contain all of the editor-specific information that an `.srs` project stores, so imported artwork may not retain its original source/layer history.

## Import .set file

Imports an existing Spiffy Roller `.set` archive.

The Set Maker extracts the archive to a temporary directory, locates `set.json`, and imports the set.

This is useful for:

- Modifying an existing set
- Using another set as a starting point
- Inspecting how a finished set was structured

For continued authoring, save the imported set as a new `.srs` project.

## Export dice set folder

Exports the current set as an unpacked folder.

The destination folder receives a subdirectory named after the Set ID.

This is useful for:

- Inspecting generated files
- Testing individual JSON/Lua/artwork files
- Manually editing or comparing output
- Preparing a set for manual packaging

If the destination already exists, the Set Maker asks before replacing it.

## Export .set file

Exports the current project as a ready-to-use Spiffy Roller `.set` file.

This is normally the final step before installing or distributing the set.

The `.set` archive contains only the files needed by Spiffy Roller. It does not preserve editor-only data such as source artwork and layer configuration.

## Exit

Closes the application.

Temporary files used when importing `.set` archives are cleaned up automatically.

---

# 4. Help Menu

## About

Displays basic information about the application and version.

---

# 5. General Tab

The **General** tab controls information that applies to the entire dice set.

It contains:

- Set properties
- Rules manifest editor
- Roll script editor

---

# 6. Set Properties

## Set name

The human-readable name displayed for the set.

Example:

```text
Shadowrun Anarchy
```

## Set ID

The internal identifier used by the set.

The Set Maker normalizes IDs when saving or exporting. Spaces and unsupported characters are converted into a safe lowercase underscore-separated identifier.

Example:

```text
shadowrun_anarchy
```

If you leave an ID blank in some editing contexts, the Set Maker may derive one from the name.

## Number of die types

Controls how many different dice appear in the set.

Enter or select a number from 1 to 32 and click **Apply**.

Increasing the count adds new die tabs.

Reducing the count permanently removes die definitions from the end of the set. The Set Maker asks for confirmation before deleting them.

---

# 7. Rules Manifest Tab

The **Rules manifest** tab contains a text editor for `rules.json`.

The default project uses a Lua rules manifest.

Use this editor when you need to change rule-engine configuration.

For the meaning of individual fields, supported engines, entry points, limits, and action handling, see:

[`custom_dice_template_guide.md`](custom_dice_template_guide.md)

## Validate rules manifest

Checks whether the contents of the editor are valid JSON and that the root is a JSON object.

This validates JSON syntax only. It does not guarantee that every field has valid Spiffy Roller semantics.

The Set Maker also performs additional checks when saving or exporting.

---

# 8. Roll Script Tab

The **Roll script** tab contains the contents of `rules.lua`.

The default script totals numeric face values.

Use this editor to implement game-specific result behavior.

Examples include:

- Counting successes
- Counting failures
- Totalling dice
- Counting symbols
- Detecting special results
- Producing custom result text
- Defining post-roll actions

For the Lua environment, `roll` structure, return format, action format, sandbox behavior, and examples, see:

[`custom_dice_template_guide.md`](custom_dice_template_guide.md)

## Validate rules.lua syntax

Checks Lua syntax using the optional Python package `luaparser`.

If the standalone Windows executable includes Lua validation support, the button works directly.

When running from source, `luaparser` must be installed:

```bash
python -m pip install luaparser
```

This button checks Lua syntax only. It does not run the script inside the Spiffy Roller firmware or verify game logic.

---

# 9. Die Tabs

Each die type has its own tab.

The tab title shows:

```text
Die 1: Name
```

The title updates as the die name changes.

Each die tab is divided into:

- Die properties
- Face list
- Selected-face metadata
- Face icon generator

---

# 10. Die Properties

## ID

Internal identifier for the die type.

Example:

```text
pool_die
```

When the die is saved, the Set Maker normalizes the ID into a safe identifier.

## Name

Human-readable die name.

Example:

```text
Pool Die
```

## Sides

Controls how many faces the die has.

Enter a value from 1 to 100 and click **Apply**.

When increasing the number of sides:

- New faces are created automatically
- Their default label/value corresponds to their face number

When decreasing the number of sides:

- Extra face definitions are deleted
- The Set Maker asks for confirmation first

## Shape

Controls the visual shape Spiffy Roller uses for the die.

Available choices are:

- `d4`
- `d6`
- `d8`
- `d10`
- `d12`
- `d20`
- `circle`
- `polygon`

The icon editor displays the currently selected shape as an outline.

## Polygon sides

Used when **Shape** is set to `polygon`.

Choose between 3 and 12 sides.

This control has no effect on the standard predefined die shapes.

## Body color

Default die body color.

You can type a hex color directly or click the `...` button to open the color chooser.

Example:

```text
#294C78
```

## Ink color

Default color used for text and 1-bit mask artwork.

You can type a hex color directly or use the color chooser.

---

# 11. Face List

The **Faces** panel shows every face of the selected die.

Each item includes the face number and a short description.

Depending on the face display mode, the list may show:

- The label
- The numeric value
- `[Blank]`
- The image name
- `[Image]`

Click a face to edit it.

Before switching to another face, the Set Maker saves the current face's metadata and artwork into the project model.

---

# 12. Selected Face Controls

The **Selected face** section controls metadata for the currently selected face.

## Label

Text associated with the face.

This can be displayed directly on the die or used by Lua rules.

Examples:

```text
Success
```

```text
GLITCH
```

```text
12
```

## Numeric value

Optional integer value associated with the face.

Leave this blank when the face has no numeric meaning.

The field accepts integers only.

## Face Display

Controls what the firmware should display on the face.

Options:

### label

Displays the face label.

### value

Displays the numeric value.

### image

Displays face artwork.

### blank

Displays no face text or image.

For details on how display modes interact with set files and firmware behavior, see the custom dice template guide.

## Image path

Shows or stores the image path associated with the face.

When artwork is generated in the built-in editor, the Set Maker creates and manages the exported image path automatically.

This field is most useful when importing or working with existing sets.

## Body override

Optional face-specific body color.

Leave blank to use the die's default body color.

## Ink override

Optional face-specific ink color.

Leave blank to use the die's default ink color.

## Symbols JSON

Optional symbol-count metadata for the face.

Enter a JSON object.

Example:

```json
{"success":1,"advantage":2}
```

Values of zero are removed when saved.

For how symbols are exposed to Lua and used by the firmware, see:

[`custom_dice_template_guide.md`](custom_dice_template_guide.md)

## Copy icon from...

Copies the complete icon data from another face on the same die.

The copied data includes:

- Artwork layers
- Palette
- Image-processing settings
- Pixel data

This is useful when several faces share similar artwork.

## Apply face metadata

Saves the currently displayed face fields into the project.

The Set Maker also saves face data automatically when switching faces and during project/export operations, but this button can be used to commit changes immediately.

---

# 13. Face Icon Generator

The **48×48 face icon generator** is used to create artwork compatible with Spiffy Roller.

The central editing canvas is enlarged for pixel-level editing, while the **Real-size preview** shows approximately how the artwork fits on the die face.

---

# 14. Icon Mode

## 1-bit mask

Best for simple icons, symbols, silhouettes, and line art.

Pixels are either:

- Transparent
- Foreground

The foreground is rendered using the die or face ink color.

Only palette color 1 is active in this mode.

Use 1-bit mask mode whenever the artwork does not need fixed internal colors.

## 4-bit indexed

Used for multicolor artwork.

The face can use up to 15 foreground palette colors plus transparency.

Palette colors become part of the exported artwork.

---

# 15. Background / Ink Interpretation

This setting controls how imported artwork is converted into foreground and transparent pixels.

The setting applies to the currently active layer.

## Black ink on white / light background

Pixels darker than the threshold are treated as foreground.

This is useful for:

- Black symbols on white
- Scanned line art
- Dark artwork on a light background

## White ink on black / dark background

Pixels brighter than the threshold are treated as foreground.

This is useful for:

- White symbols on black
- Light line art on a dark background

## Alpha only

Uses the source image's alpha channel to determine visibility.

This is generally the best choice for PNG artwork that already has a transparent background.

---

# 16. Import Image

Click **Import image...** to load artwork into the active layer.

Supported source formats include:

- PNG
- BMP
- JPG/JPEG
- GIF
- WebP

The imported image is converted to RGBA internally.

When imported:

- The image is automatically scaled to fit within the 48×48 grid
- Horizontal and vertical offsets are reset
- The source image is retained in `.srs` projects
- The current image-processing settings are applied

The imported source is not simply copied into the final set. The editor converts it into the selected 1-bit or indexed format.

---

# 17. Rebuild from Source

**Rebuild from source** reprocesses the current layer's imported source image using the current settings.

These settings include:

- Icon mode
- Interpretation mode
- Scale
- Horizontal offset
- Vertical offset
- Gamma
- Threshold

Most controls rebuild imported artwork automatically as they are adjusted.

The button is useful when you want to force a rebuild manually.

If the active layer does not have a source image, the Set Maker displays a message.

---

# 18. Clear Active Layer

Deletes the contents and source image from the currently selected layer.

The Set Maker asks for confirmation before clearing it.

Only the active layer is affected.

Other layers remain unchanged.

---

# 19. Scale Control

Controls the size of the imported source artwork on the 48×48 canvas.

The available range is approximately:

```text
10% to 400%
```

Move the slider or type a value into the field.

The artwork updates in real time.

---

# 20. Horizontal Position

The **Horz.** control moves imported artwork left or right.

Range:

```text
-48 to +48 pixels
```

Negative values move left.

Positive values move right.

---

# 21. Vertical Position

The **Vert.** control moves imported artwork up or down.

Range:

```text
-48 to +48 pixels
```

Negative values move up.

Positive values move down.

---

# 22. Gamma

Adjusts source-image luminance before thresholding or quantization.

Typical value:

```text
1.0
```

Lower or higher values can help recover details in artwork that is too dark or too light for straightforward thresholding.

This setting affects the active layer only.

---

# 23. Threshold

Controls which source pixels become visible.

Range:

```text
0 to 255
```

Its effect depends on the selected interpretation mode.

Examples:

- In **Black ink on white**, darker pixels pass the threshold.
- In **White ink on black**, brighter pixels pass.
- In **Alpha only**, pixel alpha is compared to the threshold.

Adjust this until the icon retains the detail you want without unwanted background pixels.

---

# 24. Artwork Layers

Each face supports four artwork layers.

The layer buttons appear below the main editing canvas:

```text
1  2  3  4
```

Click a number to make that layer active.

The active layer button is highlighted.

Each layer has its own:

- Pixel data
- Imported source image
- Scale
- Horizontal offset
- Vertical offset
- Gamma
- Threshold
- Interpretation mode

The icon mode and color palette are shared by the face as a whole.

## Layer order

Layer 1 is visually above later layers.

When multiple layers contain pixels in the same location, the higher layer takes precedence.

The editor shows non-active-layer pixels using a patterned representation so you can distinguish them while editing.

---

# 25. Manual Pixel Editing

The main canvas is a magnified 48×48 pixel grid.

## Left click

Paints the selected foreground color into the active layer.

In 1-bit mode, this always paints the single foreground color.

In 4-bit indexed mode, it paints the currently selected palette color.

Dragging with the left mouse button held paints continuously.

## Right click

Makes pixels transparent on the active layer.

Dragging with the right mouse button held erases continuously.

---

# 26. Shape Outline

A magenta dashed outline appears over the editor canvas.

This represents the approximate die-face boundary for the currently selected die shape.

Pixels outside the outline are not automatically deleted. The outline is a visual composition guide.

The real-size preview gives a better indication of how artwork will appear within the die shape.

---

# 27. Real-Size Preview

The **Real-size preview** shows the current face at approximately its actual display scale.

It applies:

- The selected die shape
- Die body color
- Face-specific body override
- Die ink color
- Face-specific ink override
- Current icon mode
- Current palette
- Composite artwork from all four layers

Use this preview to judge whether fine details will remain readable on the physical display.

---

# 28. Foreground Palette

The palette appears beside the editor.

## In 1-bit mode

Only the first palette color is active.

The actual exported mask will normally be rendered using the die or face ink color by Spiffy Roller.

## In 4-bit indexed mode

Up to 15 colors are available.

Click a color to select it for manual painting.

Double-click a color to edit it.

You can also select a color and click **Edit selected color...**.

The editor uses the selected palette when generating indexed artwork from imported source images.

---

# 29. Checkerboard Background

Transparent pixels are displayed over a checkerboard.

Click **Choose tint...** to change the checkerboard tint.

This does not affect exported artwork.

It is only an editor aid that can make certain artwork easier to see.

---

# 30. Saving Face and Die Data

The Set Maker generally saves current editor fields automatically when:

- Switching faces
- Changing die count
- Saving a project
- Exporting a set

There are still two explicit controls:

## Apply face metadata

Commits the currently displayed face metadata.

## Apply next to Sides

Changes the actual number of faces on the die.

Changing the spinbox alone does not resize the die until **Apply** is clicked.

---

# 31. Saving a Project

Use:

**File > Save project**

or:

**File > Save project as...**

The `.srs` project is the Set Maker's native authoring format.

Unlike a final `.set`, it preserves the source material needed for comfortable editing.

For custom artwork, this includes original imported images and transformation settings.

For that reason, do not treat a `.set` export as a replacement for your `.srs` source project.

---

# 32. Importing Existing Sets

Existing `.set` files and unpacked set directories can be imported.

The Set Maker reconstructs as much editable information as possible from the exported files.

However, final `.set` packages are designed for the firmware, not for preserving Set Maker authoring history.

As a result, imported sets may not retain:

- Original source-image resolution
- Original source filename/location
- Original layer separation
- Original transformation history

After importing a set you intend to maintain, save it as an `.srs` project.

---

# 33. Exporting a Finished Set

Before export, the Set Maker validates the current model.

For Lua-based rules it checks that:

- `rules.json` contains a JSON object
- The script reference is `rules.lua`
- The Lua source contains a `resolve` function

Use:

**File > Export .set file**

for a finished package.

The default filename is based on the Set ID.

---

# 34. Exported Artwork

When a face contains visible artwork created in the icon editor, the Set Maker writes a generated PNG into the set's `icons` directory.

The filename is based on the die ID and face number.

The Set Maker also detects identical generated icons.

If multiple faces have exactly the same:

- Icon mode
- Palette
- Composite pixel data

the exported set can reuse one image file rather than writing duplicates.

---

# 35. Exporting an Unpacked Folder

Use:

**File > Export dice set folder**

when you want to inspect the raw output.

A typical exported folder contains files such as:

```text
set.json
rules.json
rules.lua
icons/
```

The exact contents depend on the set.

For the meaning and required structure of these files, see:

[`custom_dice_template_guide.md`](custom_dice_template_guide.md)

---

# 36. Recommended Authoring Workflow

A practical workflow is:

1. Create a new set project.
2. Enter the Set name and Set ID.
3. Set the number of die types.
4. Configure each die's:
   - ID
   - Name
   - Sides
   - Shape
   - Colors
5. Define face labels, values, symbols, and display modes.
6. Create or import face artwork.
7. Use the real-size preview to check readability.
8. Configure `rules.json`.
9. Write or edit `rules.lua`.
10. Validate the JSON manifest.
11. Validate Lua syntax if available.
12. Save the project as `.srs`.
13. Export a `.set`.
14. Test the `.set` on Spiffy Roller.
15. Return to the `.srs` project for further edits.

---

# 37. Tips for Face Artwork

## Prefer simple artwork

The physical face artwork is only 48×48 pixels.

Fine lines and tiny details can disappear.

## Use 1-bit mask mode when possible

Mask artwork is:

- Smaller
- Simpler
- Compatible with die/face ink-color changes
- Easier to read at small sizes

Use indexed mode only when the face genuinely needs multiple fixed colors.

## Check the real-size preview

Artwork that looks excellent on the magnified canvas may be unreadable at actual size.

## Use layers for composite symbols

Instead of permanently merging source artwork outside the Set Maker, use layers when you may want to reposition components independently later.

## Keep the `.srs`

The `.srs` file retains imported source images and editing information that the exported `.set` does not.

---

# 38. Rules Editing Tips

The Set Maker provides text editors rather than a visual rules builder.

This is intentional because different games can require very different logic.

Use the Set Maker for editing and packaging the rules files, and use the template guide for the scripting contract.

See:

[`custom_dice_template_guide.md`](custom_dice_template_guide.md)

for:

- `rules.json` fields
- Lua entry points
- `roll` data
- Dice and face data exposed to Lua
- Returned result format
- Post-roll actions
- Limits and sandbox restrictions

---

# 39. Troubleshooting

## Export says the rules are invalid

Check the **Rules manifest** tab.

Use **Validate rules manifest** first.

For Lua-based rules, also confirm that:

- The manifest references `rules.lua`
- The Lua editor contains `function resolve`

## Lua syntax validation is unavailable

If running from source, install:

```bash
python -m pip install luaparser
```

The rest of the Set Maker can still function without it.

## Imported image disappears

Check:

- Interpretation mode
- Threshold
- Scale
- Horizontal/vertical position
- Active layer

For transparent PNGs, try **Alpha only**.

## Too much of the image becomes visible

Adjust the threshold or gamma.

Make sure the selected interpretation mode matches the source artwork.

## Palette colors look wrong

In indexed mode, imported artwork is quantized to the available palette.

Try simplifying the source image or editing palette entries after import.

## Face looks correct in the editor but not on the roller

Check:

- Face Display mode
- Body/ink overrides
- Exported `.set` contents
- Firmware compatibility

For format-level behavior, refer to the custom dice template guide.

## I changed the number of sides but nothing happened

Click **Apply** next to the Sides control.

## I reduced the number of sides and lost faces

Reducing the number of sides deletes excess face definitions after confirmation.

Recover them from an earlier `.srs` project or backup if necessary.

## An imported `.set` no longer has editable layers

Final `.set` files do not preserve original Set Maker layer history.

Use the original `.srs` project whenever possible.

---

# 40. File Format Summary

## `.srs`

Use for:

- Editing
- Archiving project sources
- Preserving artwork layers
- Preserving imported source files
- Continuing development

## `.set`

Use for:

- Installing on Spiffy Roller
- Sharing finished dice sets
- Publishing releases

## Unpacked set folder

Use for:

- Inspection
- Debugging
- Manual file editing
- Understanding exported structure

---

# 41. Related Documentation

For information about the Spiffy Roller dice-set format itself, see:

[`custom_dice_template_guide.md`](custom_dice_template_guide.md)

For the Spiffy Roller firmware and device documentation, see:

[Spiffy Roller on GitHub](https://github.com/candre23/SpiffyRoller)

---

# 42. Quick Reference

| Task | Control |
|---|---|
| Start a new project | File > New set project |
| Open editable project | File > Open existing project |
| Save editable project | File > Save project |
| Import existing set | File > Import .set file |
| Export finished set | File > Export .set file |
| Change die count | General > Number of die types > Apply |
| Change face count | Die tab > Sides > Apply |
| Select face | Faces list |
| Save face fields | Apply face metadata |
| Import artwork | Import image... |
| Reprocess artwork | Rebuild from source |
| Paint pixel | Left click |
| Erase pixel | Right click |
| Change layer | Layer buttons 1-4 |
| Edit palette color | Double-click palette color |
| Validate JSON | Validate rules manifest |
| Validate Lua syntax | Validate rules.lua syntax |
| Inspect final files | Export dice set folder |

