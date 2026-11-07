// Bounded independent CrispASR F5 baseline; not an OrTTS adapter.
#include "f5_tts.h"
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <iterator>
#include <vector>
using Clock=std::chrono::steady_clock;
static double ms(Clock::time_point t){return std::chrono::duration<double,std::milli>(Clock::now()-t).count();}
int main(int argc,char**argv){
 if(argc<4||argc>6)return 2;
 auto p=f5_tts_default_params();p.n_threads=4;p.use_gpu=false;p.seed=42;p.ode_steps=32;
 auto t=Clock::now();auto*c=f5_tts_init_from_file(argv[1],p);double load=ms(t);if(!c)return 3;
 std::ifstream f(argv[2],std::ios::binary|std::ios::ate);if(!f){f5_tts_free(c);return 4;}
 std::vector<float>x((size_t)f.tellg()/sizeof(float));f.seekg(0);f.read((char*)x.data(),x.size()*sizeof(float));
 double rms=0;for(float a:x)rms+=a*a;rms=std::sqrt(rms/x.size());if(rms>1e-10&&rms<0.1)for(auto&a:x)a*=0.1/rms;
 t=Clock::now();int ref=f5_tts_set_reference(c,x.data(),(int)x.size(),argc==6?argv[5]:"The northern wind crossed the quiet harbor.");double reference=ms(t);if(ref){f5_tts_free(c);return 5;}
 float*audio=nullptr;int sr=0;t=Clock::now();int n=f5_tts_synthesize(c,argc>=5?argv[4]:"At nine thirty, please check the train ticket and call the station.",&audio,&sr);double synth=ms(t);
 if(n<=0||!audio){f5_tts_free(c);return 6;}
 std::ofstream o(argv[3],std::ios::binary);o.write((char*)audio,n*sizeof(float));
 printf("metrics.load_ms=%f\nmetrics.reference_ms=%f\nmetrics.wall_ms=%f\nmetrics.audio_duration_ms=%f\nmetrics.rtf=%f\nmetrics.sample_rate=%d\n",load,reference,synth,1000.0*n/sr,synth*sr/(1000.0*n),sr);
 free(audio);f5_tts_free(c);return o?0:7;
}
