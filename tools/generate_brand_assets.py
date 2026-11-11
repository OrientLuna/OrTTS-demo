#!/usr/bin/env python3
"""Render the repository-native flat SVG mark into platform icon resources. No network."""
import io
import json
from pathlib import Path
import xml.etree.ElementTree as ET
import cairosvg
from PIL import Image
ROOT = Path(__file__).resolve().parents[1]
BG = '#FFF9EF'
def main():
    brand = ROOT/'assets/brand'
    svg = (brand/'ortts-mark.svg').read_text()
    # The SVG is the editable source; no photograph or generated image is processed.
    app_svg = svg.replace('<title>', f'<rect width="1024" height="1024" fill="{BG}"/><title>', 1)
    (brand/'ortts-icon.svg').write_text(app_svg)
    rgba = Image.open(io.BytesIO(cairosvg.svg2png(bytestring=app_svg.encode(),output_width=1024,output_height=1024))).convert('RGB')
    rgba.save(brand/'ortts-icon.png')
    rgba.resize((256,256),Image.Resampling.LANCZOS).save(brand/'ortts-preview.png')
    desktop_svg=svg.replace('<title>', f'<rect x="24" y="24" width="976" height="976" rx="216" fill="{BG}"/><title>',1)
    desktop=Image.open(io.BytesIO(cairosvg.svg2png(bytestring=desktop_svg.encode(),output_width=1024,output_height=1024))).convert('RGBA')
    desktop.save(brand/'ortts-desktop.png')
    desktop.save(brand/'ortts.ico',sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])
    desktop.save(brand/'ortts.icns',format='ICNS')
    assets=ROOT/'apple/Assets.xcassets';icons=assets/'AppIcon.appiconset';icons.mkdir(parents=True,exist_ok=True)
    entries=[]
    for size,scale,idiom in [(20,2,'iphone'),(20,3,'iphone'),(29,2,'iphone'),(29,3,'iphone'),(40,2,'iphone'),(40,3,'iphone'),(60,2,'iphone'),(60,3,'iphone'),(1024,1,'ios-marketing')]:
        name=f'icon-{size}-{scale}.png';rgba.resize((size*scale,size*scale),Image.Resampling.LANCZOS).save(icons/name)
        entries.append(dict(size=f'{size}x{size}',scale=f'{scale}x',idiom=idiom,filename=name))
    (icons/'Contents.json').write_text(json.dumps({'images':entries,'info':{'version':1,'author':'xcode'}},indent=2)+'\n')
    (assets/'Contents.json').write_text(json.dumps({'info':{'version':1,'author':'xcode'}},indent=2)+'\n')
    # Reuse SVG paths in an Android vector; shrink into the adaptive icon safe zone.
    tree=ET.fromstring(svg)
    lines=['<vector xmlns:android="http://schemas.android.com/apk/res/android" android:width="108dp" android:height="108dp" android:viewportWidth="108" android:viewportHeight="108">',' <group android:translateX="12.3" android:translateY="12.3" android:scaleX="0.08145" android:scaleY="0.08145">']
    def paths(node,attrs):
        attrs={**attrs,**node.attrib}
        if node.tag.endswith('path'):
            values={'pathData':attrs['d'],'fillColor':attrs.get('fill','none')}
            if values['fillColor']=='none':values['fillColor']='#00000000'
            for s,t in [('stroke','strokeColor'),('stroke-width','strokeWidth'),('stroke-linecap','strokeLineCap'),('stroke-linejoin','strokeLineJoin')]:
                if s in attrs:values[t]=attrs[s]
            lines.append('  <path '+' '.join(f'android:{k}="{v}"' for k,v in values.items())+'/>')
        for child in node:paths(child,attrs)
    paths(tree,{})
    lines+=[' </group>','</vector>']
    (ROOT/'android/app/src/main/res/drawable/ic_blocks.xml').write_text('\n'.join(lines)+'\n')
    for density,size in [('mdpi',48),('hdpi',72),('xhdpi',96),('xxhdpi',144),('xxxhdpi',192)]:
        folder=ROOT/f'android/app/src/main/res/mipmap-{density}';folder.mkdir(parents=True,exist_ok=True)
        rgba.resize((size,size),Image.Resampling.LANCZOS).save(folder/'ic_launcher.png')
if __name__=='__main__':main()
