#!/usr/bin/env fontforge
import os, fontforge

fonts_path = "./thesis/fonts"
fonts = [
    "Manrope-Regular.ttf",      # base font
    "NotoSans-Regular.ttf",
    "NotoSansJP-Regular.ttf",
    "unifont.otf",
]
fonts = [os.path.join(fonts_path, f) for f in fonts]
output = "thesis/fonts/Fontified.ttf"

print("Creating merged font:", output)
base = fontforge.open(fonts[0])
base_em = base.em  # remember base units per em

for fpath in fonts[1:]:
    print("  -> Merging", fpath)
    font = fontforge.open(fpath)
    
    # Normalize scale to base font
    scale_factor = base_em / font.em
    font.em = base_em
    font.transform([scale_factor, 0, 0, scale_factor, 0, 0])
    
    # Align baseline if needed
    font.ascent  = base.ascent
    font.descent = base.descent
    
    base.mergeFonts(font)
    font.close()

# Rename merged font
base.familyname = "Fontified"
base.fontname   = "Fontified"
base.fullname   = "Fontified"
base.encoding   = "UnicodeFull"
base.generate(output)
base.close()

print("✅ Done! Saved as", output)
