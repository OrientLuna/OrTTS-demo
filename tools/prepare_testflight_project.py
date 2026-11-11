#!/usr/bin/env python3
"""Generate a local Xcode archive project from verified installed SDKs. No upload."""
import argparse,json,plistlib,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True);p.add_argument('--engine-install',type=Path,required=True);p.add_argument('--g2p-install',type=Path,required=True);p.add_argument('--team',required=True);p.add_argument('--build',type=int,required=True);p.add_argument('--version',default='0.4.0');p.add_argument('--bundle-id',default='com.orient.ortts.prototype');a=p.parse_args()
 if a.build<1:p.error('build must be positive')
 engine=a.engine_install.resolve();g2p=a.g2p_install.resolve();out=a.out.resolve();out.mkdir(parents=True,exist_ok=True)
 for f in [engine/'OrTTS.framework/OrTTS',g2p/'espeak-ng.framework/espeak-ng',g2p/'espeak-ng-data/phontab']:
  if not f.is_file():raise ValueError('Missing installed dependency: '+str(f))
 from PIL import Image,ImageDraw
 icons=out/'Assets.xcassets/AppIcon.appiconset';icons.mkdir(parents=True,exist_ok=True);im=Image.new('RGB',(1024,1024),'#101f40');draw=ImageDraw.Draw(im)
 for i,h in enumerate([180,320,480,620,480,320,180]):
  x=210+i*88;draw.rounded_rectangle((x,512-h//2,x+52,512+h//2),radius=26,fill='#66dfd2')
 entries=[]
 for size,scale,idiom in [(20,2,'iphone'),(20,3,'iphone'),(29,2,'iphone'),(29,3,'iphone'),(40,2,'iphone'),(40,3,'iphone'),(60,2,'iphone'),(60,3,'iphone'),(1024,1,'ios-marketing')]:
  name=f'icon-{size}-{scale}.png';im.resize((size*scale,size*scale)).save(icons/name);entries.append({'size':f'{size}x{size}','scale':f'{scale}x','idiom':idiom,'filename':name})
 (icons/'Contents.json').write_text(json.dumps({'images':entries,'info':{'version':1,'author':'xcode'}}))
 info=plistlib.loads((ROOT/'apple/Info.plist').read_bytes());info.update(CFBundleIdentifier='$(PRODUCT_BUNDLE_IDENTIFIER)',CFBundleExecutable='$(EXECUTABLE_NAME)',CFBundleVersion='$(CURRENT_PROJECT_VERSION)',CFBundleShortVersionString='$(MARKETING_VERSION)',ITSAppUsesNonExemptEncryption=False)
 (out/'Info.plist').write_bytes(plistlib.dumps(info));(out/'SpeechModels.json').write_bytes((ROOT/'runtime/models/catalog.example.json').read_bytes())
 q=lambda s:json.dumps(str(s))
 text='name: OrTTS\noptions:\n  deploymentTarget:\n    iOS: "16.3"\ntargets:\n  OrTTS:\n    type: application\n    platform: iOS\n    sources:\n'
 for name in ['main.m','Demo.m','SpeechDemo.m','StreamPlayback.m','WorkQueue.m','DownloadChannels.m','OwnModelPackage.m','OwnModelCatalog.m','SharedModelFiles.m','ModelDownloadUI.m']:text+='      - path: '+q(ROOT/'apple'/name)+'\n'
 text+='      - path: Assets.xcassets\n      - path: SpeechModels.json\n        buildPhase: resources\n'
 for name in ['espeak-ng-data','licenses']:text+='      - path: '+q(g2p/name)+'\n        type: folder\n        buildPhase: resources\n'
 text+='    dependencies:\n'
 for f in [engine/'OrTTS.framework',g2p/'espeak-ng.framework']:text+='      - framework: '+q(f)+'\n        embed: true\n'
 text+='      - sdk: AVFoundation.framework\n      - sdk: UniformTypeIdentifiers.framework\n      - sdk: Network.framework\n    settings:\n      base:\n'
 settings={'PRODUCT_BUNDLE_IDENTIFIER':a.bundle_id,'INFOPLIST_FILE':'Info.plist','DEVELOPMENT_TEAM':a.team,'CODE_SIGN_STYLE':'Automatic','TARGETED_DEVICE_FAMILY':'1','HEADER_SEARCH_PATHS':str(ROOT/'runtime/include'),'CLANG_ENABLE_OBJC_ARC':'YES','GCC_PREPROCESSOR_DEFINITIONS':'$(inherited) ORTTS_APP_CPU_PROFILE=\\"arm64-baseline\\"','ASSETCATALOG_COMPILER_APPICON_NAME':'AppIcon','MARKETING_VERSION':a.version,'CURRENT_PROJECT_VERSION':str(a.build)}
 for key,value in settings.items():text+='        '+key+': '+q(value)+'\n'
 (out/'project.yml').write_text(text);subprocess.run(['xcodegen','generate','--spec',str(out/'project.yml')],check=True)
 (out/'ExportOptions.plist').write_bytes(plistlib.dumps({'method':'app-store-connect','destination':'upload','teamID':a.team,'signingStyle':'automatic','uploadSymbols':True,'manageAppVersionAndBuildNumber':False}))
 print('Project prepared; archive and export are separate explicit steps.')
if __name__=='__main__':main()
