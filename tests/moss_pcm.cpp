#include "../android/app/src/main/cpp/speech_pcm.h"
#include <filesystem>
#include <iostream>
int main(int n,char**v){if(n!=2)return 2;try{
 std::string path=std::string(v[1])+"/stereo-roundtrip.wav";
 float pcm[]={1.06758f,-0.5f,0.25f,-0.125f};speech_pcm::save(path,pcm,2,48000,2);auto a=speech_pcm::load(path);
 if(a.channels!=2||a.rate!=48000||a.frames()!=2||a.samples!=std::vector<float>(pcm,pcm+4))throw std::runtime_error("Stereo frame/float roundtrip");
 bool rejected=false;try{speech_pcm::save(path,pcm,1,48000,3);}catch(...){rejected=true;}if(!rejected)throw std::runtime_error("Wrong channels accepted");
 rejected=false;try{speech_pcm::load(std::string(v[1])+"/missing-reference.wav");}catch(...){rejected=true;}if(!rejected)throw std::runtime_error("Missing reference accepted");
 std::filesystem::remove(path);std::cout<<"PCM_STEREO_FLOAT_FRAMES_NO_CLIP_PASS\n";return 0;
}catch(const std::exception&e){std::cerr<<e.what()<<"\n";return 1;}}
