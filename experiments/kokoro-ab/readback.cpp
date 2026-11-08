#include "ortts_speech.h"
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <iostream>
#include <iterator>
#include <stdexcept>
#include <string>
#include <vector>
static uint32_t u32(const unsigned char*p){return uint32_t(p[0])|(uint32_t(p[1])<<8)|(uint32_t(p[2])<<16)|(uint32_t(p[3])<<24);}
static std::vector<float> load(const char*path){
 std::ifstream f(path,std::ios::binary);std::vector<unsigned char>b((std::istreambuf_iterator<char>(f)),{});uint32_t rate=0;std::vector<float>x;
 if(b.size()<12||memcmp(b.data(),"RIFF",4)||memcmp(b.data()+8,"WAVE",4))throw std::runtime_error("Expected WAVE");
 for(size_t p=12;p+8<=b.size();){uint32_t n=u32(b.data()+p+4);size_t start=p+8;if(n>b.size()-start)throw std::runtime_error("Truncated WAVE");
  if(!memcmp(b.data()+p,"fmt ",4)){if(n<16||b[start+2]!=1||b[start+3]||b[start+14]!=32||b[start+15]||(b[start]!=3&&!(b[start]==254&&b[start+1]==255)))throw std::runtime_error("Expected mono F32");rate=u32(b.data()+start+4);}
  if(!memcmp(b.data()+p,"data",4)){if(n%4)throw std::runtime_error("Invalid PCM size");x.resize(n/4);memcpy(x.data(),b.data()+start,n);}
  p=start+n+(n&1);
 }
 if(!rate||x.empty())throw std::runtime_error("Missing PCM");for(float v:x)if(!std::isfinite(v))throw std::runtime_error("Nonfinite PCM");
 std::vector<float>y(size_t(double(x.size())*16000/rate));for(size_t i=0;i<y.size();i++){double pos=double(i)*rate/16000;size_t j=std::min(size_t(pos),x.size()-1);y[i]=x[j]+(x[std::min(j+1,x.size()-1)]-x[j])*float(pos-j);}return y;
}
int main(int argc,char**argv){
 ortts_speech_config c{};c.struct_size=sizeof(c);c.family="sense_asr";c.model_path="local/compat/assets/sensevoice-small-q8-audiocpp-v1.gguf";c.threads=4;ortts_asr*asr=nullptr;
 if(ortts_asr_create(&c,&asr)){std::cerr<<ortts_last_error();return 1;}
 try{for(int a=1;a<argc;a++){auto pcm=load(argv[a]);ortts_transcript*t=nullptr;bool zh=std::string(argv[a]).find("-zh")!=std::string::npos;if(ortts_asr_run(asr,pcm.data(),pcm.size(),zh?"zh":"en",&t))throw std::runtime_error(ortts_last_error());std::cout<<argv[a]<<"\t"<<ortts_transcript_text(t)<<std::endl;ortts_transcript_free(t);}}
 catch(const std::exception&e){std::cerr<<e.what();ortts_asr_free(asr);return 2;}ortts_asr_free(asr);
}
