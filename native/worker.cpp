#define NOMINMAX
#include <windows.h>
#include "public.sdk/source/vst/hosting/hostclasses.h"
#include "public.sdk/source/vst/hosting/eventlist.h"
#include "public.sdk/source/vst/hosting/parameterchanges.h"
#include "public.sdk/source/vst/hosting/plugprovider.h"
#include "public.sdk/source/common/memorystream.h"
#include "public.sdk/source/vst/vstpresetfile.h"
#include "pluginterfaces/vst/ivstaudioprocessor.h"
#include "pluginterfaces/vst/ivstcomponent.h"
#include "pluginterfaces/vst/ivsteditcontroller.h"
#include "pluginterfaces/vst/ivstunits.h"
#include "pluginterfaces/vst/ivstprocesscontext.h"

#include <array>
#include <algorithm>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <sstream>
#include <vector>
#include <iomanip>
#include <cmath>
#include <map>
#include <io.h>
#include <fcntl.h>

using namespace Steinberg;
using namespace Steinberg::Vst;
namespace fs = std::filesystem;

static void require(bool success, const char* message)
{
    if (!success)
        throw std::runtime_error(message);
}

static std::vector<char> readState(const fs::path& path, uintmax_t cap=16*1024*1024)
{
    const auto size = fs::file_size(path);
    require(size <= cap, "state exceeds size limit");
    std::vector<char> bytes(size);
    std::ifstream file(path, std::ios::binary);
    file.read(bytes.data(), bytes.size());
    require(bool(file), "cannot read plugin state");
    return bytes;
}

static void writeState(const fs::path& path, MemoryStream& state)
{
    require(state.getSize()>=0 && state.getSize()<=16*1024*1024,"returned plugin state exceeds size bound");
    std::ofstream file(path, std::ios::binary);
    file.write(state.getData(), state.getSize());
    file.close();
    require(bool(file), "cannot finalize plugin state");
}

static std::string utf8(const TChar* text) {
    int length=0;while(length<128 && text[length])++length;
    int size = WideCharToMultiByte(CP_UTF8, 0, reinterpret_cast<const wchar_t*>(text), length,
                                   nullptr, 0, nullptr, nullptr);
    std::string result(size, 0);
    WideCharToMultiByte(CP_UTF8, 0, reinterpret_cast<const wchar_t*>(text), length,
                         result.data(), size, nullptr, nullptr);
    return result;
}

static std::string jsonString(const std::string& value) {
    std::ostringstream output;
    output << '"';
    for (unsigned char ch : value) {
        if (ch == '"' || ch == '\\') output << '\\' << ch;
        else if (ch < 32) output << "\\u00" << std::hex << std::setw(2) << std::setfill('0') << int(ch);
        else output << ch;
    }
    output << '"'; return output.str();
}
static bool synchronizeController(IComponent* component,IEditController* controller) {
    if(!controller)return false;
    MemoryStream state;
    if(component->getState(&state)!=kResultOk || state.getSize()<0 || state.getSize()>16*1024*1024)return false;
    state.seek(0,IBStream::kIBSeekSet,nullptr);
    return controller->setComponentState(&state)==kResultOk;
}
#include "editor_host.h"

int wmain(int argc, wchar_t** argv)
{
    try {
        std::cout<<std::setprecision(17);
        if(argc==8 && std::wstring(argv[1])==L"--parameter") {
            const std::wstring direction=argv[6],input=argv[7];
            require((direction==L"display" || direction==L"normalized") && input.size()<=127,"invalid bounded parameter conversion");
            size_t used=0;const auto requested=std::stoull(argv[5],&used);
            require(used==std::wstring(argv[5]).size() && requested<=UINT32_MAX,"invalid parameter ID");
            std::string error;auto module=VST3::Hosting::Module::create(fs::path(argv[2]).u8string(),error);require(bool(module),error.c_str());
            HostApplication host;PluginContextFactory::instance().setPluginContext(&host);
            for(const auto& info:module->getFactory().classInfos()) {
                if(info.category()!=kVstAudioEffectClass || info.ID().toString()!=fs::path(argv[3]).u8string())continue;
                PlugProvider provider(module->getFactory(),info);require(provider.initialize(),"parameter controller initialization failed");
                auto component=provider.getComponentPtr();auto controller=provider.getControllerPtr();require(bool(controller),"plugin has no controller");
                bool controllerSynced=false;
                if(std::wstring(argv[4])!=L"-") {
                    auto bytes=readState(fs::path(argv[4]));MemoryStream saved(bytes.data(),bytes.size());
                    require(component->setState(&saved)==kResultOk,"parameter component restore failed");saved.seek(0,IBStream::kIBSeekSet,nullptr);controllerSynced=controller->setComponentState(&saved)==kResultOk;
                    auto path=fs::path(argv[4]);path+=L".controller";
                    if(fs::exists(path)) {auto bytes=readState(path);MemoryStream state(bytes.data(),bytes.size());require(controller->setState(&state)==kResultOk,"parameter controller restore failed");}
                }
                else controllerSynced=synchronizeController(component,controller);
                const int count=controller->getParameterCount();require(count>=0 && count<=8192,"parameter count exceeds bound");
                ParameterInfo parameter{};bool found=false;
                for(int i=0;i<count;++i) {ParameterInfo item{};require(controller->getParameterInfo(i,item)==kResultOk,"invalid parameter metadata");if(item.id==requested){parameter=item;found=true;break;}}
                require(found,"parameter ID is unavailable");ParamValue value=0;
                if(direction==L"display") {String128 text{};std::copy(input.begin(),input.end(),text);require(controller->getParamValueByString(parameter.id,text,value)==kResultOk,"plugin rejected displayed parameter text");}
                else {used=0;value=std::stod(input,&used);require(used==input.size(),"normalized value has trailing characters");}
                require(std::isfinite(value) && value>=0 && value<=1,"converted normalized value exceeds range");
                String128 display{};const bool displayed=controller->getParamStringByValue(parameter.id,value,display)==kResultOk;
                const auto plain=controller->normalizedParamToPlain(parameter.id,value);
                std::cout<<"{\"class_id\":"<<jsonString(info.ID().toString())<<",\"id\":"<<parameter.id<<",\"normalized\":"<<value
                         <<",\"display\":"<<(displayed?jsonString(utf8(display)):"null")<<",\"plain\":"<<(std::isfinite(plain)?std::to_string(plain):"null")
                         <<",\"units\":"<<jsonString(utf8(parameter.units))<<",\"steps\":"<<parameter.stepCount<<",\"flags\":"<<parameter.flags<<",\"controller_component_synced\":"<<(controllerSynced?"true":"false")<<"}\n";
                return 0;
            }
            throw std::runtime_error("requested plugin class not found");
        }
        if(argc==3 && std::wstring(argv[1])==L"--preset-info") {
            auto bytes=readState(fs::path(argv[2]),34*1024*1024);
            MemoryStream stream(bytes.data(),bytes.size());PresetFile preset(&stream);
            require(preset.readChunkList() && preset.contains(kComponentState),"invalid component preset");
            for(int i=0;i<preset.getEntryCount();++i) {
                const auto& entry=preset.at(i);
                require(entry.offset>=48 && entry.size>=0 && entry.size<=16*1024*1024 &&
                            static_cast<uintmax_t>(entry.offset)<=bytes.size() &&
                            static_cast<uintmax_t>(entry.size)<=bytes.size()-entry.offset,"invalid preset chunk range");
            }
            char classID[33]{};preset.getClassID().toString(classID);
            std::cout<<"{\"class_id\":"<<jsonString(classID)<<",\"chunks\":"<<preset.getEntryCount()<<"}\n";
            return 0;
        }
        if ((argc==6 || argc==7) && (std::wstring(argv[1])==L"--editor" || std::wstring(argv[1])==L"--save-state")) {
            std::string error;
            auto module=VST3::Hosting::Module::create(fs::path(argv[2]).u8string(),error);
            require(bool(module),error.c_str());
            HostApplication application;PluginContextFactory::instance().setPluginContext(&application);
            const auto chosen=fs::path(argv[3]).u8string();
            for (const auto& info:module->getFactory().classInfos()) {
                if(info.category()!=kVstAudioEffectClass || info.ID().toString()!=chosen) continue;
                PlugProvider provider(module->getFactory(),info);
                require(provider.initialize(),"editor plugin initialization failed");
                auto component=provider.getComponentPtr();auto controller=provider.getControllerPtr();
                require(bool(controller),"plugin has no controller");
                bool controllerSynced=false;
                if (std::wstring(argv[4])!=L"-") {
                    auto bytes=readState(fs::path(argv[4]));MemoryStream state(bytes.data(),bytes.size());
                    require(component->setState(&state)==kResultOk,"editor component restore failed");
                    state.seek(0,IBStream::kIBSeekSet,nullptr);controllerSynced=controller->setComponentState(&state)==kResultOk;
                    auto path=fs::path(argv[4]);path+=L".controller";
                    if(fs::exists(path)) {auto data=readState(path);MemoryStream saved(data.data(),data.size());
                        require(controller->setState(&saved)==kResultOk,"editor controller restore failed");}
                }
                else controllerSynced=synchronizeController(component,controller);
                FUnknownPtr<IAudioProcessor> processor(component);
                std::map<ParamID,ParamValue> initial;
                if(argc==7) {
                    require(fs::file_size(fs::path(argv[6]))<=64000,"initial editor edits exceed size bound");
                    std::ifstream input{fs::path(argv[6])};std::string line;
                    require(controller->getParameterCount()<=8192,"editor parameter count exceeds bound");
                    while(std::getline(input,line)) {
                        std::istringstream fields(line);ParamID id;ParamValue value;std::string extra;
                        require(bool(fields>>id>>value) && !(fields>>extra) && std::isfinite(value) && value>=0 && value<=1,
                                "invalid initial editor parameter");
                        bool found=false;
                        for(int i=0;i<controller->getParameterCount();++i) {
                            ParameterInfo parameter{};controller->getParameterInfo(i,parameter);
                            if(parameter.id==id && !(parameter.flags&ParameterInfo::kIsReadOnly))found=true;
                        }
                        require(found,"unknown or read-only editor parameter");initial[id]=value;
                    }
                }
                editPlugin(component,processor,controller,initial,std::wstring(argv[1])==L"--editor");
                MemoryStream state;
                require(component->getState(&state)==kResultOk,"editor component save failed");
                writeState(fs::path(argv[5]),state);
                MemoryStream saved;
                if(controller->getState(&saved)==kResultOk) {auto path=fs::path(argv[5]);path+=L".controller";writeState(path,saved);}
                std::cout<<"{\"class_id\":"<<jsonString(chosen)<<",\"state_saved\":true,\"controller_component_synced\":"<<(controllerSynced?"true":"false")<<",\"parameter_values\":{";
                for(int i=0;i<controller->getParameterCount();++i) {
                    ParameterInfo parameter{};controller->getParameterInfo(i,parameter);
                    if(i)std::cout<<',';
                    std::cout<<jsonString(std::to_string(parameter.id))<<':'<<controller->getParamNormalized(parameter.id);
                }
                std::cout<<"}}\n";return 0;
            }
            throw std::runtime_error("requested plugin class not found");
        }
        const bool inspecting = (argc == 3 || argc==5) && std::wstring(argv[1]) == L"--inspect";
        if (inspecting) {
            std::string error;
            auto module = VST3::Hosting::Module::create(fs::path(argv[2]).u8string(), error);
            require(bool(module), error.c_str());
            HostApplication host;
            PluginContextFactory::instance().setPluginContext(&host);
            std::cout << "{\"classes\":[";
            bool first = true;
            for (const auto& info : module->getFactory().classInfos()) {
                if (info.category() != kVstAudioEffectClass) continue;
                if(argc==5 && info.ID().toString()!=fs::path(argv[4]).u8string())continue;
                PlugProvider provider(module->getFactory(), info);
                require(provider.initialize(), "inspection initialization failed");
                bool controllerSynced=false;
                if(argc==5 && std::wstring(argv[3])!=L"-") {
                    auto component=provider.getComponentPtr();auto controller=provider.getControllerPtr();
                    auto bytes=readState(fs::path(argv[3]));MemoryStream saved(bytes.data(),bytes.size());
                    require(component->setState(&saved)==kResultOk,"inspection component restore failed");
                    if(controller) {
                        saved.seek(0,IBStream::kIBSeekSet,nullptr);controllerSynced=controller->setComponentState(&saved)==kResultOk;
                        auto path=fs::path(argv[3]);path+=L".controller";
                        if(fs::exists(path)) {auto data=readState(path);MemoryStream state(data.data(),data.size());
                            require(controller->setState(&state)==kResultOk,"inspection controller restore failed");}
                    }
                }
                auto component = provider.getComponentPtr();
                auto controller = provider.getControllerPtr();
                if(argc!=5 || std::wstring(argv[3])==L"-")controllerSynced=synchronizeController(component,controller);
                FUnknownPtr<IUnitInfo> units(controller);std::map<UnitID,ProgramListID> programUnits;
                const int unitCount=units?units->getUnitCount():0;require(unitCount>=0 && unitCount<=512,"unit count exceeds bound");
                for(int i=0;i<unitCount;++i) {UnitInfo unit{};require(units->getUnitInfo(i,unit)==kResultOk,"invalid unit information");programUnits[unit.id]=unit.programListId;}
                if (!first) std::cout << ',';
                first = false;
                std::cout << "{\"class_id\":" << jsonString(info.ID().toString())
                          << ",\"name\":" << jsonString(info.name())
                          << ",\"vendor\":" << jsonString(info.vendor())
                          << ",\"version\":" << jsonString(info.version())
                          << ",\"audio_inputs\":" << component->getBusCount(kAudio,kInput)
                          << ",\"audio_outputs\":" << component->getBusCount(kAudio,kOutput)
                          << ",\"controller_component_synced\":"<<(controllerSynced?"true":"false")
                          << ",\"parameters\":[";
                const int count = controller ? controller->getParameterCount() : 0;
                require(count >= 0 && count <= 8192, "parameter count exceeds bound");
                for (int i=0; i<count; ++i) {
                    ParameterInfo parameter{};
                    require(controller->getParameterInfo(i, parameter) == kResultOk, "invalid parameter");
                    if (i) std::cout << ',';
                    const auto value=controller->getParamNormalized(parameter.id);require(std::isfinite(value) && value>=0 && value<=1,"plugin reported invalid normalized value");
                    String128 display{};const bool displayed=controller->getParamStringByValue(parameter.id,value,display)==kResultOk;
                    std::cout << "{\"id\":" << parameter.id << ",\"name\":" << jsonString(utf8(parameter.title))
                              << ",\"units\":" << jsonString(utf8(parameter.units))
                              << ",\"normalized\":" << value << ",\"display\":"<<(displayed?jsonString(utf8(display)):"null")
                              << ",\"unit_id\":"<<parameter.unitId<<",\"program_list_id\":"
                              << ((parameter.flags&ParameterInfo::kIsProgramChange) && programUnits.count(parameter.unitId)?std::to_string(programUnits[parameter.unitId]):"null")
                              << ",\"steps\":" << parameter.stepCount << ",\"flags\":" << parameter.flags << '}';
                }
                std::cout << "],\"program_lists\":[";
                const int lists=units?units->getProgramListCount():0;require(lists>=0 && lists<=128,"program list count exceeds bound");int nameBudget=64;
                for(int i=0;i<lists;++i) {
                    ProgramListInfo list{};require(units->getProgramListInfo(i,list)==kResultOk && list.programCount>=0 && list.programCount<=65536,"invalid program list");
                    if(i)std::cout<<',';const int names=std::min(list.programCount,nameBudget);nameBudget-=names;
                    std::cout<<"{\"id\":"<<list.id<<",\"name\":"<<jsonString(utf8(list.name))<<",\"count\":"<<list.programCount<<",\"names\":[";
                    for(int j=0;j<names;++j) {if(j)std::cout<<',';String128 name{};bool ok=units->getProgramName(list.id,j,name)==kResultOk;std::cout<<(ok?jsonString(utf8(name)):"null");}
                    std::cout<<"],\"names_truncated\":"<<(names<list.programCount?"true":"false")<<'}';
                }
                std::cout << "]}";
            }
            std::cout << "]}\n"; return 0;
        }
        require(argc >= 6 && argc <= 10,
                "usage: arranger-vst3 plugin input.f32 output.f32 state-in-or-- state-out [midi-pitch]");
        const bool eventStreaming=std::getenv("ARRANGER_STREAM_EVENTS")!=nullptr;
        require(!eventStreaming || (std::wstring(argv[2])==L"-" && std::wstring(argv[3])==L"-" &&
                    argc>=9 && std::wstring(argv[6])==L"-" && std::wstring(argv[7])==L"-"),
                "event packets require explicit-class streaming without file notes/automation");
        std::vector<std::pair<int64, Event>> scheduled;
        if (argc >= 7 && std::wstring(argv[6]) != L"-") {
            auto addNote = [&](int64 start, int64 end, int pitch, int velocity) {
                require(start >= 0 && end > start && end < 242 * 44100 && pitch >= 0
                            && pitch <= 127 && velocity >= 1 && velocity <= 127
                            && scheduled.size() < 4096, "invalid MIDI note");
                Event on{}, off{};
                on.type = Event::kNoteOnEvent;
                off.type = Event::kNoteOffEvent;
                on.noteOn.pitch = off.noteOff.pitch = static_cast<int16>(pitch);
                on.noteOn.noteId = off.noteOff.noteId = static_cast<int32>(scheduled.size() / 2 + 1);
                on.noteOn.velocity = velocity / 127.0f;
                scheduled.emplace_back(start, on);
                scheduled.emplace_back(end, off);
            };
            std::wstring argument(argv[6]);
            if (argument.front() == L'@') {
                std::ifstream notes{fs::path(argument.substr(1))};
                require(bool(notes), "cannot read MIDI notes");
                std::string line;
                while (std::getline(notes, line)) {
                    std::istringstream fields(line);
                    int64 start, end;
                    int pitch, velocity;
                    std::string extra;
                    require(bool(fields >> start >> end >> pitch >> velocity) && !(fields >> extra),
                            "MIDI row must contain start, end, pitch and velocity");
                    addNote(start, end, pitch, velocity);
                }
            } else {
                size_t consumed = 0;
                int pitch = std::stoi(argument, &consumed);
                require(consumed == argument.size(), "invalid MIDI pitch");
                addNote(0, 22050, pitch, 102);
            }
            std::stable_sort(scheduled.begin(), scheduled.end(), [](const auto& a, const auto& b) {
                if (a.first != b.first)
                    return a.first < b.first;
                return a.second.type == Event::kNoteOffEvent && b.second.type != Event::kNoteOffEvent;
            });
            require(scheduled.empty() || fs::file_size(fs::path(argv[2])) / 8 > static_cast<uintmax_t>(scheduled.back().first),
                    "MIDI note-off must fit within the input frame count");
        }
        std::string error;
        auto module = VST3::Hosting::Module::create(fs::path(argv[1]).u8string(), error);
        if (!module)
            throw std::runtime_error(error);
        HostApplication host;
        PluginContextFactory::instance().setPluginContext(&host);
        const auto& factory = module->getFactory();
        const auto classes = factory.classInfos();
        for (const auto& info : classes) {
            if (info.category() != kVstAudioEffectClass)
                continue;
            if (argc>=9 && std::wstring(argv[8])!=L"-" && fs::path(argv[8]).u8string()!=info.ID().toString()) continue;
            PlugProvider provider(factory, info);
            require(provider.initialize(), "plugin initialization failed");
            auto component = provider.getComponentPtr();
            FUnknownPtr<IAudioProcessor> processor(component);
            const bool instrument = eventStreaming || (argc>=7 && std::wstring(argv[6])!=L"-");
            const int inputCount=component->getBusCount(kAudio,kInput);
            const int outputCount=component->getBusCount(kAudio,kOutput);
            const bool hasSidechain=argc==10 && std::wstring(argv[9])!=L"-";
            if (!processor || (instrument ? inputCount!=0 : inputCount<1 || inputCount>2)
                    || outputCount<1 || outputCount>8 || (hasSidechain && inputCount!=2))
                continue;
            const bool streamingInput=std::wstring(argv[2])==L"-";
            require(!streamingInput || !hasSidechain,"stream protocol does not accept a file sidechain");
            if(!streamingInput)require(fs::file_size(fs::path(argv[2]))*outputCount<=512ULL*1024*1024,
                                      "multi-output render exceeds 512MiB output allocation cap");
            std::ifstream sidechain;
            if(hasSidechain) {
                require(fs::file_size(fs::path(argv[9]))==fs::file_size(fs::path(argv[2])),"sidechain frame count differs from main input");
                sidechain.open(fs::path(argv[9]),std::ios::binary);
                require(bool(sidechain),"cannot open sidechain");
            }
            struct Change { int64 frame; ParamID id; double value; };
            std::vector<Change> automation;
            if (argc >= 8 && std::wstring(argv[7])!=L"-") {
                std::ifstream file{fs::path(argv[7])};
                require(bool(file), "cannot read automation");
                auto controller = provider.getControllerPtr();
                require(bool(controller), "automation requires controller");
                require(controller->getParameterCount()>=0 && controller->getParameterCount()<=8192,
                        "automation parameter count exceeds bound");
                std::string line;
                while (std::getline(file, line)) {
                    std::istringstream fields(line); Change change{}; std::string extra;
                    require(bool(fields >> change.frame >> change.id >> change.value) && !(fields >> extra)
                                && change.frame >= 0 && change.frame < 242 * 44100
                                && std::isfinite(change.value) && change.value >= 0 && change.value <= 1
                                && automation.size() < 8192, "invalid automation point");
                    bool found = false;
                    for (int i=0; i<controller->getParameterCount(); ++i) {
                        ParameterInfo parameter{}; controller->getParameterInfo(i,parameter);
                        if (parameter.id == change.id && !(parameter.flags & ParameterInfo::kIsReadOnly)) found = true;
                    }
                    require(found, "unknown or read-only automation parameter");
                    automation.push_back(change);
                }
                std::stable_sort(automation.begin(),automation.end(),[](const auto& a,const auto& b){return a.frame<b.frame;});
            }
            bool componentRestored=false,controllerRestored=false,controllerSynced=false;
            if (std::wstring(argv[4]) != L"-") {
                const fs::path statePath(argv[4]);
                auto bytes = readState(statePath);
                MemoryStream state(bytes.data(), static_cast<TSize>(bytes.size()));
                require(component->setState(&state) == kResultOk, "component rejected state");
                componentRestored=true;
                if (auto controller = provider.getControllerPtr()) {
                    state.seek(0, IBStream::kIBSeekSet, nullptr);
                    controllerSynced=controller->setComponentState(&state)==kResultOk;
                    auto controllerPath = statePath;
                    controllerPath += L".controller";
                    if (fs::exists(controllerPath)) {
                        auto controllerBytes = readState(controllerPath);
                        MemoryStream savedController(controllerBytes.data(), controllerBytes.size());
                        require(controller->setState(&savedController) == kResultOk,
                                "controller rejected saved state");
                        controllerRestored=true;
                    }
                }
            }
            if(std::wstring(argv[4])==L"-")controllerSynced=synchronizeController(component,provider.getControllerPtr());
            std::array<SpeakerArrangement,2> inputLayouts{SpeakerArr::kStereo,SpeakerArr::kStereo};
            std::array<SpeakerArrangement,8> outputLayouts{};
            outputLayouts.fill(SpeakerArr::kStereo);
            if(processor->setBusArrangements(instrument ? nullptr : inputLayouts.data(),inputCount,
                                            outputLayouts.data(),outputCount)!=kResultOk) {
                for(int bus=0;bus<inputCount;++bus)
                    require(processor->getBusArrangement(kInput,bus,inputLayouts[bus])==kResultOk &&
                            (inputLayouts[bus]==SpeakerArr::kMono || inputLayouts[bus]==SpeakerArr::kStereo),
                            "plugin native input is not mono/stereo");
                for(int bus=0;bus<outputCount;++bus)
                    require(processor->getBusArrangement(kOutput,bus,outputLayouts[bus])==kResultOk &&
                            (outputLayouts[bus]==SpeakerArr::kMono || outputLayouts[bus]==SpeakerArr::kStereo),
                            "plugin native output is not mono/stereo");
                require(processor->setBusArrangements(instrument?nullptr:inputLayouts.data(),inputCount,
                            outputLayouts.data(),outputCount)==kResultOk,"plugin rejected its native mono/stereo layout");
            }
            std::array<int,2> inputChannels{};std::array<int,8> outputChannels{};
            for(int bus=0;bus<inputCount;++bus)inputChannels[bus]=SpeakerArr::getChannelCount(inputLayouts[bus]);
            for(int bus=0;bus<outputCount;++bus)outputChannels[bus]=SpeakerArr::getChannelCount(outputLayouts[bus]);
            constexpr int block = 512;
            ProcessSetup setup{kOffline, kSample32, block, 44100.0};
            require(processor->setupProcessing(setup) == kResultOk, "processing setup failed");
            if (instrument) {
                require(component->getBusCount(kEvent, kInput) > 0, "missing MIDI event input");
                component->activateBus(kEvent, kInput, 0, true);
            } else {
                component->activateBus(kAudio, kInput, 0, true);
                if(inputCount==2)component->activateBus(kAudio,kInput,1,hasSidechain);
            }
            for(int bus=0;bus<outputCount;++bus)component->activateBus(kAudio,kOutput,bus,true);
            require(component->setActive(true) == kResultOk, "activation failed");
            processor->setProcessing(true);
            const bool streaming = std::wstring(argv[2]) == L"-";
            const bool pipeOutput = std::wstring(argv[3]) == L"-";
            uint32 streamOutputBus=0;
            if(pipeOutput && std::getenv("ARRANGER_STREAM_OUTPUT_BUS")) {
                const std::string text=std::getenv("ARRANGER_STREAM_OUTPUT_BUS");size_t used=0;
                const auto value=std::stoul(text,&used);require(used==text.size() && value<static_cast<uint32>(outputCount),"stream output bus is unavailable");streamOutputBus=static_cast<uint32>(value);
            }
            std::ifstream inputFile;
            std::ofstream outputFile;
            std::array<std::ofstream,7> extraOutputs;
            if (streaming) _setmode(_fileno(stdin), _O_BINARY);
            else inputFile.open(fs::path(argv[2]), std::ios::binary);
            if (pipeOutput) _setmode(_fileno(stdout), _O_BINARY);
            else outputFile.open(fs::path(argv[3]), std::ios::binary);
            for(int bus=1;!pipeOutput && bus<outputCount;++bus) {
                auto path=fs::path(argv[3]);path+=L".bus"+std::to_wstring(bus);
                extraOutputs[bus-1].open(path,std::ios::binary);
                require(bool(extraOutputs[bus-1]),"cannot open additional output bus");
            }
            std::istream& input = streaming ? std::cin : inputFile;
            std::ostream& output = pipeOutput ? std::cout : outputFile;
            require(bool(input) && bool(output), "cannot open audio files");
            std::array<float, block * 2> interleaved{};
            std::array<float,block*2> auxiliary{};
            float inputSamples[2][2][block]{}, outputSamples[8][2][block]{};
            float* inputs[2][2]{};
            float* outputs[8][2]{};
            std::array<AudioBusBuffers,2> in{};
            std::array<AudioBusBuffers,8> out{};
            for(int bus=0;bus<inputCount;++bus) {
                for(int ch=0;ch<2;++ch)inputs[bus][ch]=inputSamples[bus][ch];
                in[bus].numChannels=inputChannels[bus];in[bus].channelBuffers32=inputs[bus];
                in[bus].silenceFlags=(bus==1 && !hasSidechain)?3:0;
            }
            for(int bus=0;bus<outputCount;++bus) {
                for(int ch=0;ch<2;++ch)outputs[bus][ch]=outputSamples[bus][ch];
                out[bus].numChannels=outputChannels[bus];out[bus].channelBuffers32=outputs[bus];
            }
            ProcessData data{};
            ProcessContext context{};
            context.sampleRate=44100;
            context.state=ProcessContext::kPlaying|ProcessContext::kContTimeValid;
            if(const auto* value=std::getenv("ARRANGER_TEMPO")) {
                size_t consumed=0;context.tempo=std::stod(value,&consumed);
                require(consumed==std::string(value).size() && std::isfinite(context.tempo) && context.tempo>=40 && context.tempo<=240,
                        "invalid explicit project tempo");
                context.timeSigNumerator=4;context.timeSigDenominator=4;
                context.state|=ProcessContext::kTempoValid|ProcessContext::kTimeSigValid|
                    ProcessContext::kProjectTimeMusicValid|ProcessContext::kBarPositionValid;
            }
            data.processContext=&context;
            data.processMode = kOffline;
            data.symbolicSampleSize = kSample32;
            data.numInputs = inputCount;
            data.numOutputs = outputCount;
            data.inputs = instrument ? nullptr : in.data();
            data.outputs = out.data();
            EventList events(eventStreaming?256:static_cast<int32>(scheduled.size()));
            data.inputEvents = instrument ? &events : nullptr;
            ParameterChanges parameters(8192);
            data.inputParameterChanges = &parameters;
            size_t nextChange = 0;
            int64 frame = 0;
            size_t nextEvent = 0;
            const auto latency = processor->getLatencySamples();
            const auto tail = processor->getTailSamples();
            double streamGain=1;
            if(eventStreaming && std::getenv("ARRANGER_STREAM_GAIN")) {
                std::istringstream value(std::getenv("ARRANGER_STREAM_GAIN"));std::string extra;
                require(bool(value>>streamGain) && !(value>>extra) && std::isfinite(streamGain) && streamGain>=-4 && streamGain<=4,
                        "continuous instrument gain exceeds bounded route range");
            }
            require(!eventStreaming || latency<=88200,"continuous instrument latency exceeds two seconds");
            if(pipeOutput && std::getenv("ARRANGER_STREAM_READY"))
                std::cerr<<"{\"ready\":true,\"latency_samples\":"<<latency<<",\"tail_samples\":"<<tail<<",\"output_buses\":"<<outputCount<<",\"selected_output_bus\":"<<streamOutputBus<<"}\n"<<std::flush;
            std::vector<std::array<float,2>> dryDelay(eventStreaming?latency:0);
            size_t dryPosition=0;
            std::array<bool,4096> held{};
            int heldCount=0;
            while (true) {
                if(eventStreaming) {
                    std::array<uint32_t,3> header{};
                    input.read(reinterpret_cast<char*>(header.data()),sizeof(header));
                    if(input.gcount()==0 && input.eof())break;
                    require(input.gcount()==sizeof(header) && header[0]==0x31565241 && header[1]>0 &&
                                header[1]<=block && header[2]<=256,"invalid bounded event packet header");
                    data.numSamples=header[1];events.clear();
                    uint32_t previousOffset=0;
                    for(uint32_t i=0;i<header[2];++i) {
                        std::array<uint32_t,5> note{};
                        input.read(reinterpret_cast<char*>(note.data()),sizeof(note));
                        require(input.gcount()==sizeof(note) && note[0]<header[1] && note[0]>=previousOffset &&
                                    note[1]<=1 && note[2]<=127 && note[3]<=127 && note[4]>0 && note[4]<held.size(),
                                "invalid bounded stream note");
                        previousOffset=note[0];
                        require(note[1]?!held[note[4]]:held[note[4]],"stream note ID lifecycle mismatch");
                        held[note[4]]=note[1];heldCount+=note[1]?1:-1;
                        require(heldCount<=128,"stream polyphony exceeds128 voices");
                        Event event{};event.sampleOffset=note[0];
                        event.type=note[1]?Event::kNoteOnEvent:Event::kNoteOffEvent;
                        if(note[1]) {event.noteOn.pitch=note[2];event.noteOn.velocity=note[3]/127.0f;event.noteOn.noteId=note[4];}
                        else {event.noteOff.pitch=note[2];event.noteOff.noteId=note[4];}
                        require(events.addEvent(event)==kResultOk,"stream event queue full");
                    }
                    input.read(reinterpret_cast<char*>(interleaved.data()),data.numSamples*8);
                    require(input.gcount()==data.numSamples*8,"incomplete event packet audio");
                } else {
                    input.read(reinterpret_cast<char*>(interleaved.data()),sizeof(interleaved));
                    if(input.gcount()==0)break;
                    require(input.gcount()%8==0,"incomplete PCM frame");
                    data.numSamples=static_cast<int32>(input.gcount()/8);
                }
                context.projectTimeSamples=context.continousTimeSamples=frame;
                if(context.state&ProcessContext::kTempoValid) {
                    context.projectTimeMusic=frame*context.tempo/(44100.0*60);
                    context.barPositionMusic=std::floor(context.projectTimeMusic/4)*4;
                }
                parameters.clearQueue();
                while (nextChange < automation.size() && automation[nextChange].frame < frame + data.numSamples) {
                    const auto& change = automation[nextChange++];
                    int32 queueIndex = 0, pointIndex = 0;
                    auto* queue = parameters.addParameterData(change.id,queueIndex);
                    require(queue && queue->addPoint(static_cast<int32>(change.frame-frame),change.value,pointIndex)==kResultOk,
                            "automation queue full");
                    provider.getControllerPtr()->setParamNormalized(change.id,change.value);
                }
                if (instrument && !eventStreaming) {
                    events.clear();
                    while (nextEvent < scheduled.size() &&
                           scheduled[nextEvent].first < frame + data.numSamples) {
                        auto event = scheduled[nextEvent].second;
                        event.sampleOffset = static_cast<int32>(scheduled[nextEvent++].first - frame);
                        require(events.addEvent(event) == kResultOk, "MIDI event buffer full");
                    }
                }
                require(streamingInput || frame+data.numSamples<=242*44100,"offline input exceeds duration budget");
                if(inputCount)for (int i = 0; i < data.numSamples; ++i)
                    for (int ch = 0; ch < inputChannels[0]; ++ch)
                        inputs[0][ch][i] = inputChannels[0]==1?0.5f*(interleaved[2*i]+interleaved[2*i+1]):interleaved[2*i+ch];
                if(hasSidechain) {
                    sidechain.read(reinterpret_cast<char*>(auxiliary.data()),data.numSamples*8);
                    require(sidechain.gcount()==data.numSamples*8,"incomplete sidechain block");
                    for(int i=0;i<data.numSamples;++i)for(int ch=0;ch<inputChannels[1];++ch)
                        inputs[1][ch][i]=inputChannels[1]==1?0.5f*(auxiliary[2*i]+auxiliary[2*i+1]):auxiliary[2*i+ch];
                }
                for(int bus=0;bus<outputCount;++bus)out[bus].silenceFlags=0;
                require(processor->process(data) == kResultOk, "plugin process failed");
                require(processor->getLatencySamples()==latency,"plugin latency changed during render; reconfigure before retrying");
                if(eventStreaming)for(int i=0;i<data.numSamples;++i) {
                    std::array<float,2> dry{interleaved[2*i],interleaved[2*i+1]};
                    auto aligned=dry;
                    if(latency) {aligned=dryDelay[dryPosition];dryDelay[dryPosition]=dry;dryPosition=(dryPosition+1)%latency;}
                    for(int ch=0;ch<2;++ch)auxiliary[2*i+ch]=aligned[ch];
                }
                for(int bus=0;bus<outputCount;++bus) {
                    if(pipeOutput && static_cast<uint32>(bus)!=streamOutputBus)continue;
                    for (int i = 0; i < data.numSamples; ++i)
                        for (int ch = 0; ch < 2; ++ch)
                        {
                            const auto channel=outputChannels[bus]==1?0:ch;
                            auto sample=(out[bus].silenceFlags & (1ULL << channel)) ? 0 : outputs[bus][channel][i];
                            if(eventStreaming && static_cast<uint32>(bus)==streamOutputBus)sample=static_cast<float>(sample*streamGain)+auxiliary[2*i+ch];
                            require(std::isfinite(sample),"plugin returned non-finite audio");
                            interleaved[2*i+ch]=sample;
                        }
                    std::ostream& destination=pipeOutput || bus==0?output:extraOutputs[bus-1];
                    destination.write(reinterpret_cast<const char*>(interleaved.data()),data.numSamples*8);
                    if(pipeOutput)destination.flush();
                    require(bool(destination),"cannot write processed audio bus");
                }
                frame += data.numSamples;
            }
            require(input.eof(), "audio read failed");
            require(!eventStreaming || heldCount==0,"stream ended with unreleased notes");
            processor->setProcessing(false);
            component->setActive(false);
            MemoryStream state;
            require(component->getState(&state) == kResultOk, "plugin did not return state");
            const fs::path statePath(argv[5]);
            if (statePath != L"-") writeState(statePath, state);
            if (auto controller = provider.getControllerPtr()) {
                MemoryStream controllerState;
                if (statePath != L"-" && controller->getState(&controllerState) == kResultOk) {
                    auto controllerPath = statePath;
                    controllerPath += L".controller";
                    writeState(controllerPath, controllerState);
                }
            }
            if (!pipeOutput) outputFile.close();
            for(int bus=1;!pipeOutput && bus<outputCount;++bus) {extraOutputs[bus-1].close();require(bool(extraOutputs[bus-1]),"cannot finalize output bus");}
            require(bool(output), "cannot finalize render files");
            auto& report = pipeOutput ? std::cerr : std::cout;
            require(nextChange == automation.size(), "automation exceeds render length");
            report << "{\"class_id\":" << jsonString(info.ID().toString())
                   << ",\"name\":" << jsonString(info.name()) << ",\"version\":" << jsonString(info.version())
                   << ",\"automation_points\":" << nextChange
                   << ",\"component_state_restored\":" << (componentRestored?"true":"false")
                   << ",\"controller_state_restored\":" << (controllerRestored?"true":"false")
                   << ",\"controller_component_synced\":" << (controllerSynced?"true":"false")
                   << ",\"output_buses\":" << outputCount << ",\"sidechain_active\":" << (hasSidechain?"true":"false")
                   << ",\"stream_output_bus\":"<<(pipeOutput?std::to_string(streamOutputBus):"null")
                   << ",\"latency_samples\":" << latency << ",\"tail_samples\":" << tail;
            report<<",\"input_channels\":[";
            for(int bus=0;bus<inputCount;++bus) {if(bus)report<<',';report<<inputChannels[bus];}
            report<<"],\"output_channels\":[";
            for(int bus=0;bus<outputCount;++bus) {if(bus)report<<',';report<<outputChannels[bus];}
            report<<"]}\n";
            return 0;
        }
        throw std::runtime_error("no VST3 audio component found");
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
