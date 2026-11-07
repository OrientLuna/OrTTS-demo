// Experiment only: whisper.cpp v1.7.6 with the existing OrTTS ggml libraries.
#include "whisper.h"
#include <chrono>
#include <cstdio>
#include <fstream>
#include <vector>
int main(int argc,char**argv){
 if(argc!=3&&argc!=4)return 2;
 auto params=whisper_context_default_params();params.use_gpu=false;
 auto start=std::chrono::steady_clock::now();auto*c=whisper_init_from_file_with_params(argv[1],params);if(!c)return 3;
 double load=std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-start).count();
 std::ifstream f(argv[2],std::ios::binary|std::ios::ate);if(!f){whisper_free(c);return 4;}auto bytes=f.tellg();if(bytes<=0||bytes%4){whisper_free(c);return 5;}
 std::vector<float>pcm(size_t(bytes)/4);f.seekg(0);f.read((char*)pcm.data(),bytes);
 auto p=whisper_full_default_params(WHISPER_SAMPLING_BEAM_SEARCH);p.n_threads=4;p.language=argc==4?argv[3]:"en";p.no_timestamps=true;p.print_progress=false;p.print_realtime=false;p.print_timestamps=false;p.print_special=false;p.beam_search.beam_size=5;
 start=std::chrono::steady_clock::now();int status=whisper_full(c,p,pcm.data(),int(pcm.size()));double wall=std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-start).count();
 printf("load_ms=%.3f\ninference_ms=%.3f\nrtf=%.6f\ntext=",load,wall,wall*16/pcm.size());if(!status)for(int i=0;i<whisper_full_n_segments(c);++i)printf("%s",whisper_full_get_segment_text(c,i));puts("");whisper_free(c);return status;
}
