#pragma once
#include <array>
#include <cstdint>
#include <fstream>
#include <iomanip>
#include <sstream>
#include <stdexcept>
#include <string>

// Small, dependency-free SHA-256 for model asset binding. Streaming:
// model files are never loaded into memory for hashing.
namespace ortts_sha256 {
inline uint32_t rotate(uint32_t x, unsigned n) { return (x >> n) | (x << (32 - n)); }
struct State {
    std::array<uint32_t, 8> h{{0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
                                0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19}};
    std::array<uint8_t, 64> block{};
    uint64_t size = 0;
    size_t filled = 0;
    void transform() {
        static constexpr uint32_t k[64] = {
            0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
            0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
            0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
            0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
            0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
            0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
            0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
            0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2};
        uint32_t w[64];
        for (unsigned i=0;i<16;++i) w[i]=(uint32_t(block[i*4])<<24)|(uint32_t(block[i*4+1])<<16)|
                                      (uint32_t(block[i*4+2])<<8)|block[i*4+3];
        for (unsigned i=16;i<64;++i) {
            auto s0=rotate(w[i-15],7)^rotate(w[i-15],18)^(w[i-15]>>3);
            auto s1=rotate(w[i-2],17)^rotate(w[i-2],19)^(w[i-2]>>10);
            w[i]=w[i-16]+s0+w[i-7]+s1;
        }
        auto a=h[0],b=h[1],c=h[2],d=h[3],e=h[4],f=h[5],g=h[6],z=h[7];
        for (unsigned i=0;i<64;++i) {
            auto s1=rotate(e,6)^rotate(e,11)^rotate(e,25);
            auto t1=z+s1+((e&f)^(~e&g))+k[i]+w[i];
            auto s0=rotate(a,2)^rotate(a,13)^rotate(a,22);
            auto t2=s0+((a&b)^(a&c)^(b&c));
            z=g;g=f;f=e;e=d+t1;d=c;c=b;b=a;a=t1+t2;
        }
        h[0]+=a;h[1]+=b;h[2]+=c;h[3]+=d;h[4]+=e;h[5]+=f;h[6]+=g;h[7]+=z;
    }
    void update(const uint8_t* data, size_t count) {
        size+=count;
        for (size_t i=0;i<count;++i) {
            block[filled++]=data[i];
            if (filled==64) { transform();filled=0; }
        }
    }
    std::string finish() {
        const uint64_t bits=size*8;
        block[filled++]=0x80;
        if (filled>56) { while(filled<64) block[filled++]=0;transform();filled=0; }
        while(filled<56) block[filled++]=0;
        for (unsigned i=0;i<8;++i) block[56+i]=uint8_t(bits>>(56-8*i));
        transform();
        std::ostringstream out;out<<std::hex<<std::setfill('0');
        for (uint32_t x:h) out<<std::setw(8)<<x;
        return out.str();
    }
};
inline std::string file(const std::string& path) {
    std::ifstream in(path,std::ios::binary);
    if (!in) throw std::runtime_error("SHA-256 input missing: "+path);
    State state;std::array<uint8_t,65536> buffer{};
    while (in) { in.read(reinterpret_cast<char*>(buffer.data()),buffer.size());
                 auto n=in.gcount();if (n>0) state.update(buffer.data(),size_t(n)); }
    if (!in.eof()) throw std::runtime_error("SHA-256 input read failed: "+path);
    return state.finish();
}
} // namespace ortts_sha256
