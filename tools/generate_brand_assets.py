#!/usr/bin/env python3
"""Export platform sizes from the approved transparent PNG master. No network or redrawing."""
import base64
import json
from pathlib import Path
from PIL import Image
ROOT=Path(__file__).resolve().parents[1]
# Ordinary iOS light icons require an opaque fallback. Use a palette-derived teal, never a white frame.
IOS_BACKGROUND='#087C75'
def main():
    brand=ROOT/'assets/brand'
    master=Image.open(brand/'ortts-master.png').convert('RGBA')
    icon=master.resize((1024,1024),Image.Resampling.LANCZOS)
    icon.save(brand/'ortts-icon.png');icon.save(brand/'ortts-desktop.png')
    icon.resize((256,256),Image.Resampling.LANCZOS).save(brand/'ortts-preview.png')
    icon.save(brand/'ortts.ico',sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])
    icon.save(brand/'ortts.icns',format='ICNS')
    # Compatibility SVG wrappers embed the approved raster; they are not hand-redrawn vector artwork.
    encoded=base64.b64encode((brand/'ortts-master.png').read_bytes()).decode()
    svg=f'<svg xmlns="http://www.w3.org/2000/svg" width="1024" height="1024" viewBox="0 0 1024 1024"><title>OrTTS approved tricolor block logo</title><image width="1024" height="1024" href="data:image/png;base64,{encoded}"/></svg>\n'
    for name in ['ortts-mark.svg','ortts-icon.svg']:(brand/name).write_text(svg)
    opaque=Image.new('RGBA',icon.size,IOS_BACKGROUND);opaque.alpha_composite(icon);opaque=opaque.convert('RGB')
    opaque.resize((256,256),Image.Resampling.LANCZOS).save(brand/'ortts-ios-preview.png')
    assets=ROOT/'apple/Assets.xcassets';icons=assets/'AppIcon.appiconset';icons.mkdir(parents=True,exist_ok=True)
    entries=[]
    for size,scale,idiom in [(20,2,'iphone'),(20,3,'iphone'),(29,2,'iphone'),(29,3,'iphone'),(40,2,'iphone'),(40,3,'iphone'),(60,2,'iphone'),(60,3,'iphone'),(1024,1,'ios-marketing')]:
        name=f'icon-{size}-{scale}.png';opaque.resize((size*scale,size*scale),Image.Resampling.LANCZOS).save(icons/name)
        entries.append(dict(size=f'{size}x{size}',scale=f'{scale}x',idiom=idiom,filename=name))
    icon.save(icons/'icon-dark.png')
    entries.append({'size':'1024x1024','scale':'1x','idiom':'ios-marketing','filename':'icon-dark.png','appearances':[{'appearance':'luminosity','value':'dark'}]})
    (icons/'Contents.json').write_text(json.dumps({'images':entries,'info':{'version':1,'author':'xcode'}},indent=2)+'\n')
    (assets/'Contents.json').write_text(json.dumps({'info':{'version':1,'author':'xcode'}},indent=2)+'\n')
    res=ROOT/'android/app/src/main/res';drawable=res/'drawable-nodpi';drawable.mkdir(parents=True,exist_ok=True)
    icon.save(drawable/'ortts_logo.png')
    (res/'drawable/ic_blocks.xml').write_text('<inset xmlns:android="http://schemas.android.com/apk/res/android" android:inset="18dp"><bitmap android:src="@drawable/ortts_logo" android:gravity="fill" android:filter="true" /></inset>\n')
    for density,size in [('mdpi',48),('hdpi',72),('xhdpi',96),('xxhdpi',144),('xxxhdpi',192)]:
        folder=res/f'mipmap-{density}';folder.mkdir(parents=True,exist_ok=True)
        icon.resize((size,size),Image.Resampling.LANCZOS).save(folder/'ic_launcher.png')
if __name__=='__main__':main()
