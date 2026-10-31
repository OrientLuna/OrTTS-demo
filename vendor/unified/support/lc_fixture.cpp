#include "lc_client.h"
#include <fstream>
#include <string>
#include <cstdlib>
#include <stdexcept>
#include <iostream>
int main(int argc,char**argv){try{if(argc!=6)throw std::runtime_error("assets variant z.raw output stream");setenv("ORTTS_LC_ASSETS",argv[1],1);setenv("ORTTS_LC_VARIANT",argv[2],1);std::ifstream f(argv[3],std::ios::binary|std::ios::ate);if(!f||f.tellg()%2048)throw std::runtime_error("z shape");std::vector<float>z(size_t(f.tellg())/4);f.seekg(0);f.read((char*)z.data(),z.size()*4);LCClient c(4);c.reset();std::vector<float>all;LCReply r;if(std::stoi(argv[5])){for(size_t i=0;i<z.size();i+=512){auto a=c.push({z.begin()+i,z.begin()+i+512},false,r);all.insert(all.end(),a.begin(),a.end());}auto a=c.push({},true,r);all.insert(all.end(),a.begin(),a.end());}else all=c.push(z,true,r);std::ofstream out(argv[4],std::ios::binary);out.write((char*)all.data(),all.size()*4);if(!out||all.size()!=z.size()/512*1920)throw std::runtime_error("PCM length");return 0;}catch(const std::exception&e){std::cerr<<e.what()<<"\n";return 1;}}
