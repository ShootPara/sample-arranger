#include <windows.h>
#include <mmsystem.h>
#include <mmreg.h>
#include <array>
#include <iostream>
#include <io.h>
#include <fcntl.h>
#include <atomic>
#include <mutex>

static std::atomic<unsigned long long> consumed{0};
static std::mutex reporting;
static void CALLBACK completed(HWAVEOUT, UINT message, DWORD_PTR, DWORD_PTR first, DWORD_PTR)
{
    if (message == WOM_DONE) {
        auto* header = reinterpret_cast<WAVEHDR*>(first);
        std::lock_guard<std::mutex> guard(reporting);
        consumed += header->dwBufferLength / 8;
        std::cout << consumed.load() << std::endl;
    }
}

// Fixed-size buffers remain alive until waveOut acknowledges consumption.
int main()
{
    _setmode(_fileno(stdin), _O_BINARY);
    WAVEFORMATEX format{};
    format.wFormatTag = WAVE_FORMAT_IEEE_FLOAT;
    format.nChannels = 2;
    format.nSamplesPerSec = 44100;
    format.wBitsPerSample = 32;
    format.nBlockAlign = 8;
    format.nAvgBytesPerSec = 352800;
    HWAVEOUT device{};
    if (waveOutOpen(&device, WAVE_MAPPER, &format,
                    reinterpret_cast<DWORD_PTR>(completed), 0, CALLBACK_FUNCTION) != MMSYSERR_NOERROR)
        return 2;
    constexpr int count = 4;
    std::array<std::array<char, 35280>, count> buffers{};
    std::array<WAVEHDR, count> headers{};
    int index = 0;
    int error = 0;
    while (std::cin) {
        auto& header = headers[index];
        while ((header.dwFlags & WHDR_INQUEUE) != 0) Sleep(1);
        if ((header.dwFlags & WHDR_PREPARED) != 0)
            waveOutUnprepareHeader(device, &header, sizeof(header));
        std::cin.read(buffers[index].data(), buffers[index].size());
        const auto bytes = std::cin.gcount();
        if (bytes == 0) break;
        if (bytes % 8) { error = 3; break; }
        header = {};
        header.lpData = buffers[index].data();
        header.dwBufferLength = static_cast<DWORD>(bytes);
        if (waveOutPrepareHeader(device, &header, sizeof(header)) ||
            waveOutWrite(device, &header, sizeof(header))) { error = 4; break; }
        index = (index + 1) % count;
    }
    for (auto& header : headers)
        while ((header.dwFlags & WHDR_INQUEUE) != 0) Sleep(1);
    // WinMM completion can precede endpoint presentation. Keep the stream open
    // for one bounded device-buffer interval before reset/close truncates its end.
    Sleep(100);
    waveOutReset(device);
    for (auto& header : headers)
        if (header.dwFlags & WHDR_PREPARED)
            waveOutUnprepareHeader(device, &header, sizeof(header));
    waveOutClose(device);
    return error;
}
