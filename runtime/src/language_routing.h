#pragma once
#include <cctype>
#include <cstdint>
#include <stdexcept>
#include <string>
#include <string_view>

namespace ortts::language {

inline std::string normalize_explicit_language(std::string_view raw) {
    size_t start = 0;
    size_t end = raw.size();
    while (start < end && std::isspace(static_cast<unsigned char>(raw[start]))) {
        ++start;
    }
    while (end > start && std::isspace(static_cast<unsigned char>(raw[end - 1]))) {
        --end;
    }
    if (start == end) {
        return "auto";
    }
    std::string key;
    key.reserve(end - start);
    for (size_t i = start; i < end; ++i) {
        char ch = static_cast<char>(std::tolower(static_cast<unsigned char>(raw[i])));
        if (ch == '_') {
            ch = '-';
        }
        key.push_back(ch);
    }
    if (key == "auto") {
        return "auto";
    }
    if (key == "chinese" || key == "zh" || key == "zh-cn" || key == "zh-hans" ||
        key == "zh-hant" || key == "zh-tw" || key == "zh-hk" || key == "cmn") {
        return "Chinese";
    }
    if (key == "english" || key == "en" || key == "en-us" || key == "en-gb" ||
        key == "en-au" || key == "en-ca") {
        return "English";
    }
    if (key == "japanese" || key == "ja" || key == "ja-jp" || key == "jp") {
        return "Japanese";
    }
    if (key == "korean" || key == "ko" || key == "ko-kr") {
        return "Korean";
    }
    if (key == "german" || key == "de" || key == "de-de") {
        return "German";
    }
    if (key == "french" || key == "fr" || key == "fr-fr") {
        return "French";
    }
    if (key == "russian" || key == "ru" || key == "ru-ru") {
        return "Russian";
    }
    if (key == "portuguese" || key == "pt" || key == "pt-br" || key == "pt-pt") {
        return "Portuguese";
    }
    if (key == "spanish" || key == "es" || key == "es-es") {
        return "Spanish";
    }
    if (key == "italian" || key == "it" || key == "it-it") {
        return "Italian";
    }
    throw std::invalid_argument("Unsupported language: " + std::string(raw.substr(start, end - start)));
}

inline uint32_t next_utf8_codepoint(const unsigned char*& p, const unsigned char* end) {
    uint8_t b0 = *p++;
    if (b0 < 0x80) {
        return b0;
    }
    int len = 0;
    uint32_t cp = 0;
    uint32_t min_cp = 0;
    if ((b0 & 0xE0) == 0xC0) {
        len = 2;
        cp = b0 & 0x1F;
        min_cp = 0x80;
    } else if ((b0 & 0xF0) == 0xE0) {
        len = 3;
        cp = b0 & 0x0F;
        min_cp = 0x800;
    } else if ((b0 & 0xF8) == 0xF0) {
        len = 4;
        cp = b0 & 0x07;
        min_cp = 0x10000;
    } else {
        return 0xFFFD;
    }
    if (end - p < len - 1) {
        p = end;
        return 0xFFFD;
    }
    for (int i = 1; i < len; ++i) {
        uint8_t bx = p[i - 1];
        if ((bx & 0xC0) != 0x80) {
            return 0xFFFD;
        }
        cp = (cp << 6) | (bx & 0x3F);
    }
    p += (len - 1);
    if (cp < min_cp || cp > 0x10FFFF || (cp >= 0xD800 && cp <= 0xDFFF)) {
        return 0xFFFD;
    }
    return cp;
}

inline std::string detect_language_from_text(std::string_view text) {
    bool has_kana = false;
    bool has_hangul = false;
    bool has_han = false;
    bool has_cyrillic = false;
    bool has_latin = false;
    bool has_cjk_punct = false;

    const auto* p = reinterpret_cast<const unsigned char*>(text.data());
    const auto* end = p + text.size();
    while (p < end) {
        const uint32_t cp = next_utf8_codepoint(p, end);
        if ((cp >= 0x3040 && cp <= 0x30FF) || (cp >= 0x31F0 && cp <= 0x31FF) || (cp >= 0xFF66 && cp <= 0xFF9D)) {
            has_kana = true;
        } else if ((cp >= 0xAC00 && cp <= 0xD7AF) || (cp >= 0x1100 && cp <= 0x11FF) ||
                   (cp >= 0x3130 && cp <= 0x318F) || (cp >= 0xA960 && cp <= 0xA97F) ||
                   (cp >= 0xD7B0 && cp <= 0xD7FF)) {
            has_hangul = true;
        } else if ((cp >= 0x4E00 && cp <= 0x9FFF) || (cp >= 0x3400 && cp <= 0x4DBF) ||
                   (cp >= 0xF900 && cp <= 0xFAFF) || (cp >= 0x20000 && cp <= 0x2EBEF) ||
                   (cp >= 0x30000 && cp <= 0x323AF)) {
            has_han = true;
        } else if (cp >= 0x0400 && cp <= 0x052F) {
            has_cyrillic = true;
        } else if ((cp >= 'A' && cp <= 'Z') || (cp >= 'a' && cp <= 'z') ||
                   (cp >= 0x00C0 && cp <= 0x024F && cp != 0x00D7 && cp != 0x00F7)) {
            has_latin = true;
        } else if ((cp >= 0x3000 && cp <= 0x303F) || (cp >= 0xFF01 && cp <= 0xFF60)) {
            has_cjk_punct = true;
        }
    }

    if (has_kana) return "Japanese";
    if (has_hangul) return "Korean";
    if (has_han) return "Chinese";
    if (has_cyrillic) return "Russian";
    if (has_latin) return "English";
    if (has_cjk_punct) return "Chinese";
    return "English";
}

inline std::string resolve_language(const char* explicit_language, std::string_view text) {
    if (explicit_language != nullptr) {
        std::string normalized = normalize_explicit_language(explicit_language);
        if (normalized != "auto") {
            return normalized;
        }
    }
    return detect_language_from_text(text);
}

} // namespace ortts::language
