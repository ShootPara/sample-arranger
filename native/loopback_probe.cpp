// Diagnostic only: capture the specified synthetic renderer's process tree.
// Never opens a microphone or falls back to whole-endpoint loopback.
#include <windows.h>
#include <mmdeviceapi.h>
#include <audioclient.h>
#include <propidl.h>
#include <atomic>
#include <fstream>
#include <iostream>
#include <vector>

struct ProcessActivation { int type; DWORD pid; int mode; };
class Completion final : public IActivateAudioInterfaceCompletionHandler {
    std::atomic<ULONG> refs{1};
public:
    HANDLE done = CreateEventW(nullptr, TRUE, FALSE, nullptr);
    HRESULT result = E_PENDING;
    IAudioClient* client = nullptr;
    ~Completion() { if (client) client->Release(); CloseHandle(done); }
    HRESULT STDMETHODCALLTYPE QueryInterface(REFIID iid, void** value) override {
        if (iid == __uuidof(IUnknown) || iid == __uuidof(IActivateAudioInterfaceCompletionHandler)
                || iid == __uuidof(IAgileObject)) {
            *value = static_cast<IActivateAudioInterfaceCompletionHandler*>(this);
            AddRef(); return S_OK;
        }
        *value = nullptr; return E_NOINTERFACE;
    }
    ULONG STDMETHODCALLTYPE AddRef() override { return ++refs; }
    ULONG STDMETHODCALLTYPE Release() override { auto count = --refs; if (!count) delete this; return count; }
    HRESULT STDMETHODCALLTYPE ActivateCompleted(IActivateAudioInterfaceAsyncOperation* operation) override {
        IUnknown* unknown = nullptr;
        auto hr = operation->GetActivateResult(&result, &unknown);
        if (FAILED(hr)) result = hr;
        if (SUCCEEDED(result) && unknown) result = unknown->QueryInterface(IID_PPV_ARGS(&client));
        if (unknown) unknown->Release();
        SetEvent(done); return S_OK;
    }
};

int main(int argc, char** argv) {
    if (argc != 4) { std::cerr << "usage: probe synthetic-renderer-pid seconds output-f32\n"; return 1; }
    const DWORD pid = std::stoul(argv[1]);
    const double seconds = std::stod(argv[2]);
    if (!pid || seconds <= 0 || seconds > 30) return 1;
    CoInitializeEx(nullptr, COINIT_MULTITHREADED);
    auto* completion = new Completion;
    ProcessActivation activation{1, pid, 0}; // PROCESS_LOOPBACK / INCLUDE_TARGET_PROCESS_TREE
    PROPVARIANT params{};
    params.vt = VT_BLOB;
    params.blob.cbSize = sizeof(activation);
    params.blob.pBlobData = reinterpret_cast<BYTE*>(&activation);
    IActivateAudioInterfaceAsyncOperation* operation = nullptr;
    auto hr = ActivateAudioInterfaceAsync(L"VAD\\Process_Loopback", __uuidof(IAudioClient),
                                          &params, completion, &operation);
    if (SUCCEEDED(hr)) {
        if (WaitForSingleObject(completion->done, 10000) != WAIT_OBJECT_0) hr = HRESULT_FROM_WIN32(WAIT_TIMEOUT);
        else hr = completion->result;
    }
    if (FAILED(hr)) { std::cerr << "process-loopback activation HRESULT 0x" << std::hex << hr << '\n'; return 2; }
    WAVEFORMATEX format{WAVE_FORMAT_IEEE_FLOAT, 2, 44100, 352800, 8, 32, 0};
    auto* client = completion->client;
    hr = client->Initialize(AUDCLNT_SHAREMODE_SHARED, AUDCLNT_STREAMFLAGS_LOOPBACK,
                            1000000, 0, &format, nullptr);
    if (FAILED(hr)) { std::cerr << "initialize HRESULT 0x" << std::hex << hr << '\n'; return 3; }
    IAudioCaptureClient* capture = nullptr;
    hr = client->GetService(IID_PPV_ARGS(&capture));
    if (FAILED(hr)) return 4;
    std::ofstream output(argv[3], std::ios::binary);
    if (!output) return 5;
    hr = client->Start();
    if (FAILED(hr)) return 6;
    std::cout << "ready" << std::endl;
    const auto deadline = GetTickCount64() + static_cast<ULONGLONG>(seconds * 1000);
    unsigned long long total = 0;
    while (GetTickCount64() < deadline) {
        UINT32 available = 0;
        hr = capture->GetNextPacketSize(&available);
        if (FAILED(hr)) break;
        while (available) {
            BYTE* data = nullptr; UINT32 frames = 0; DWORD flags = 0;
            hr = capture->GetBuffer(&data, &frames, &flags, nullptr, nullptr);
            if (FAILED(hr)) break;
            if (flags & AUDCLNT_BUFFERFLAGS_SILENT) {
                std::vector<char> silence(frames * 8);
                output.write(silence.data(), silence.size());
            } else output.write(reinterpret_cast<char*>(data), frames * 8);
            total += frames;
            capture->ReleaseBuffer(frames);
            hr = capture->GetNextPacketSize(&available);
            if (FAILED(hr)) break;
        }
        if (FAILED(hr)) break;
        Sleep(2);
    }
    client->Stop(); capture->Release(); operation->Release(); completion->Release();
    output.close(); CoUninitialize();
    std::cout << "frames " << total << std::endl;
    return FAILED(hr) || !output ? 7 : 0;
}
