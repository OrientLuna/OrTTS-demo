#pragma once
#include <cmath>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <stdexcept>
#include <string>
#include <vector>
namespace speech_pcm {
struct Audio {std::vector<float> samples;int rate=0,channels=0;size_t frames()const{return samples.size()/channels;}};
inline std::string read(const std::string&p){std::ifstream f(p,std::ios::binary);if(!f)throw std::runtime_error("Missing reference/trace: "+p);return {std::istreambuf_iterator<char>(f),{}};}
inline uint32_t le(const std::string&b,size_t p,int n){if(p+n>b.size())throw std::runtime_error("Truncated WAV");uint32_t v=0;for(int i=0;i<n;i++)v|=uint32_t(uint8_t(b[p+i]))<<(8*i);return v;}
inline Audio load(const std::string&p){
 auto b=read(p);if(b.size()>32*1024*1024||b.size()<12||b.substr(0,4)!="RIFF"||b.substr(8,4)!="WAVE")throw std::runtime_error("Reference WAV schema");
 Audio a;size_t offset=0,bytes=0;int fmt=0,bits=0,align=0;
 for(size_t i=12;i+8<=b.size();){size_t n=le(b,i+4,4);if(n>b.size()-i-8)throw std::runtime_error("Truncated WAV chunk");if(b.compare(i,4,"fmt ")==0){if(n<16)throw std::runtime_error("WAV fmt");fmt=le(b,i+8,2);a.channels=le(b,i+10,2);a.rate=le(b,i+12,4);align=le(b,i+20,2);bits=le(b,i+22,2);}else if(b.compare(i,4,"data")==0){offset=i+8;bytes=n;}i+=8+n+(n&1);}
 if(!offset||!bytes||a.channels<1||a.channels>2||a.rate<8000||a.rate>192000||!((fmt==1&&bits==16)||(fmt==3&&bits==32))||align!=a.channels*bits/8||bytes%align)throw std::runtime_error("Reference WAV format/channels");
 for(size_t i=offset;i<offset+bytes;i+=bits/8){auto u=le(b,i,bits/8);float x;if(fmt==1)x=int16_t(u)/32768.f;else std::memcpy(&x,&u,4);if(!std::isfinite(x))throw std::runtime_error("Nonfinite reference");a.samples.push_back(x);}
 return a;
}
inline void u(std::ostream&f,uint32_t v,int n){for(int i=0;i<n;i++)f.put(char(v>>(8*i)));}
inline void save(const std::string&p,const float*x,size_t frames,int rate,int channels){
 if(!x||!frames||(channels!=1&&channels!=2)||rate<8000||rate>192000||frames>size_t(rate)*120)throw std::runtime_error("Output PCM schema");
 size_t n=frames*channels;
 for(size_t i=0;i<n;i++)if(!std::isfinite(x[i]))throw std::runtime_error("Nonfinite output");
 std::ofstream f(p,std::ios::binary);f.write("RIFF",4);u(f,36+n*4,4);f.write("WAVEfmt ",8);u(f,16,4);u(f,3,2);u(f,channels,2);u(f,rate,4);u(f,rate*channels*4,4);u(f,channels*4,2);u(f,32,2);f.write("data",4);u(f,n*4,4);f.write(reinterpret_cast<const char*>(x),n*4);if(!f)throw std::runtime_error("WAV write failed");
}
}
