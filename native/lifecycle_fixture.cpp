// Owned lifecycle fixture: no audio/input/network. Sleeps until its parent is killed.
#include <windows.h>
#include <fstream>
#include <string>
#include <filesystem>
#include <iostream>

int wmain(int argc,wchar_t** argv) {
    if(argc==3 && std::wstring(argv[1])==L"--hold-memory") {
        wchar_t* end=nullptr;unsigned long mib=wcstoul(argv[2],&end,10);
        if(!end || *end || mib<16 || mib>512)return 6;
        void* allocation=VirtualAlloc(nullptr,static_cast<SIZE_T>(mib)*1024*1024,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE);
        if(!allocation) {std::cout<<"denied\n"<<std::flush;return 0;}
        std::cout<<"held\n"<<std::flush;std::string release;std::getline(std::cin,release);
        VirtualFree(allocation,0,MEM_RELEASE);return 0;
    }
    if(argc==2 && std::wstring(argv[1])==L"--probe-memory") {
        void* allocation=VirtualAlloc(nullptr,256ULL*1024*1024,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE);
        if(allocation) {VirtualFree(allocation,0,MEM_RELEASE);return 9;}
        return GetLastError()==ERROR_NOT_ENOUGH_QUOTA || GetLastError()==ERROR_COMMITMENT_LIMIT ||
               GetLastError()==ERROR_NOT_ENOUGH_MEMORY?0:8;
    }
    if(argc==2 && std::wstring(argv[1])==L"--sleep") {Sleep(60000);return 0;}
    if(argc!=2)return 1;
    wchar_t path[32768]{};GetModuleFileNameW(nullptr,path,32768);
    std::wstring command=L"\""+std::wstring(path)+L"\" --sleep";
    STARTUPINFOW startup{};startup.cb=sizeof(startup);PROCESS_INFORMATION child{};
    if(!CreateProcessW(path,command.data(),nullptr,nullptr,FALSE,CREATE_NO_WINDOW,nullptr,nullptr,&startup,&child))return 2;
    std::ofstream output{std::filesystem::path(argv[1])};
    output<<'['<<GetCurrentProcessId()<<','<<child.dwProcessId<<']';output.close();
    WaitForSingleObject(child.hProcess,60000);CloseHandle(child.hThread);CloseHandle(child.hProcess);return 0;
}
