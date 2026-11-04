#define NOMINMAX
#include <windows.h>
#include "public.sdk/source/vst/vstaudioeffect.h"
#include "public.sdk/source/common/pluginview.h"
#include "public.sdk/source/vst/vsteditcontroller.h"
#include "public.sdk/source/main/pluginfactory.h"
#include "pluginterfaces/base/ibstream.h"
#include "pluginterfaces/vst/ivstevents.h"
#include "pluginterfaces/vst/ivstparameterchanges.h"
#include "pluginterfaces/vst/ivstprocesscontext.h"
#include <array>
#include <cstdlib>

using namespace Steinberg;
using namespace Steinberg::Vst;

class DelayFixture : public AudioEffect {
    std::array<std::array<float, 384>, 2> memory{};
    std::array<std::array<float,384>,2> auxiliary{};
    int cursor = 0;
    bool instrument;
    bool routing;
    bool mono;
    float level = 0;
    std::array<bool,4096> held{};
    int voices=0;
    float gain = 1;
    int64 expectedFrame=0;
public:
    explicit DelayFixture(bool synth = false,bool routed=false,bool single=false) : instrument(synth),routing(routed),mono(single) {
        setControllerClass(FUID(0x66231002, 0x14424231, 0xA5621002, 0x12142801));
    }
    static FUnknown* create(void*) { return static_cast<IAudioProcessor*>(new DelayFixture); }
    static FUnknown* synth(void*) { return static_cast<IAudioProcessor*>(new DelayFixture(true)); }
    static FUnknown* routed(void*) { return static_cast<IAudioProcessor*>(new DelayFixture(false,true)); }
    static FUnknown* monoEffect(void*) { return static_cast<IAudioProcessor*>(new DelayFixture(false,false,true)); }
    static FUnknown* monoSynth(void*) { return static_cast<IAudioProcessor*>(new DelayFixture(true,false,true)); }
    tresult PLUGIN_API initialize(FUnknown* context) override {
        if(std::getenv("ARRANGER_FIXTURE_INITIALIZE_CRASH"))std::abort();
        auto result = AudioEffect::initialize(context);
        if (result != kResultOk) return result;
        if (instrument) addEventInput(STR16("Notes"), 1);
        else addAudioInput(mono?STR16("Mono"):STR16("Stereo"),mono?SpeakerArr::kMono:SpeakerArr::kStereo);
        if(routing)addAudioInput(STR16("Sidechain"),SpeakerArr::kStereo,kAux);
        addAudioOutput(mono?STR16("Mono"):STR16("Stereo"),mono?SpeakerArr::kMono:SpeakerArr::kStereo);
        if(routing)addAudioOutput(STR16("Difference"),SpeakerArr::kStereo,kAux);
        return kResultOk;
    }
    tresult PLUGIN_API setBusArrangements(SpeakerArrangement* inputs,int32 count,SpeakerArrangement* outputs,int32 outCount) override {
        if(mono) {
            if(count!=(instrument?0:1) || outCount!=1 || outputs[0]!=SpeakerArr::kMono ||
                (!instrument && inputs[0]!=SpeakerArr::kMono))return kResultFalse;
            return kResultOk;
        }
        return AudioEffect::setBusArrangements(inputs,count,outputs,outCount);
    }
    tresult PLUGIN_API canProcessSampleSize(int32 size) override {
        return size == kSample32 ? kResultOk : kResultFalse;
    }
    uint32 PLUGIN_API getLatencySamples() override { return 128; }
    uint32 PLUGIN_API getTailSamples() override { return 256; }
    tresult PLUGIN_API getState(IBStream* stream) override {
        int32 version = 2;
        if (stream->write(&version,sizeof(version)) != kResultOk) return kResultFalse;
        return stream->write(&gain,sizeof(gain));
    }
    tresult PLUGIN_API setState(IBStream* stream) override {
        int32 version = 0;
        if (stream->read(&version,sizeof(version)) != kResultOk || version != 2) return kResultFalse;
        return stream->read(&gain,sizeof(gain));
    }
    tresult PLUGIN_API process(ProcessData& data) override {
        if (std::getenv("ARRANGER_FIXTURE_CRASH")) std::abort();
        if (std::getenv("ARRANGER_FIXTURE_CHECK_CONTEXT")) {
            const auto* context=data.processContext;
            if(!context || !(context->state&ProcessContext::kTempoValid) || context->tempo!=137 ||
                context->sampleRate!=44100 || context->projectTimeSamples!=expectedFrame ||
                context->continousTimeSamples!=expectedFrame || context->timeSigNumerator!=4 ||
                context->timeSigDenominator!=4) return kResultFalse;
            expectedFrame+=data.numSamples;
        }
        data.outputs[0].silenceFlags = 0;
        for (int i = 0; i < data.numSamples; ++i) {
            if (data.inputParameterChanges) {
                for (int q=0;q<data.inputParameterChanges->getParameterCount();++q) {
                    auto* queue = data.inputParameterChanges->getParameterData(q);
                    if (queue->getParameterId()!=1) continue;
                    for (int p=0;p<queue->getPointCount();++p) {
                        int32 offset=0; ParamValue value=0;
                        if (queue->getPoint(p,offset,value)==kResultOk && offset==i) gain=static_cast<float>(value);
                    }
                }
            }
            if (instrument && data.inputEvents) {
                for (int n = 0; n < data.inputEvents->getEventCount(); ++n) {
                    Event event{};
                    data.inputEvents->getEvent(n, event);
                    if (event.sampleOffset == i) {
                        if (event.type == Event::kNoteOnEvent) {
                            auto id=event.noteOn.noteId;
                            if(id<0 || id>=4096 || held[id] || voices>=128)return kInvalidArgument;
                            held[id]=true;++voices;
                        }
                        if (event.type == Event::kNoteOffEvent) {
                            auto id=event.noteOff.noteId;
                            if(id<0 || id>=4096 || !held[id])return kInvalidArgument;
                            held[id]=false;--voices;
                        }
                        level=0.25f*voices;
                    }
                }
            }
            for (int ch = 0; ch < (mono?1:2); ++ch) {
                auto& ring = memory[ch];
                ring[cursor] = gain * (instrument ? level : data.inputs[0].channelBuffers32[ch][i]);
                data.outputs[0].channelBuffers32[ch][i] =
                    ring[(cursor + 384 - 128) % 384] +
                    0.5f * ring[(cursor + 384 - 256) % 384];
                if(routing) {
                    auto& side=auxiliary[ch];
                    side[cursor]=gain*data.inputs[1].channelBuffers32[ch][i];
                    auto delayed=side[(cursor+384-128)%384];
                    data.outputs[0].channelBuffers32[ch][i]+=0.25f*delayed;
                    data.outputs[1].channelBuffers32[ch][i]=ring[(cursor+384-128)%384]-delayed;
                }
            }
            cursor = (cursor + 1) % 384;
        }
        return kResultOk;
    }
};

class FixtureView : public CPluginView {
    EditController* controller;
    HWND child=nullptr;
    static LRESULT CALLBACK procedure(HWND window,UINT message,WPARAM first,LPARAM second) {
        auto* view=reinterpret_cast<FixtureView*>(GetWindowLongPtrW(window,GWLP_USERDATA));
        if (view && message==WM_COMMAND && LOWORD(first)==1) {
            auto value=view->controller->getParamNormalized(1)>0?0.0:1.0;
            view->controller->beginEdit(1);view->controller->setParamNormalized(1,value);
            view->controller->performEdit(1,value);view->controller->endEdit(1);
            SetWindowTextW(GetDlgItem(window,1),value>0?L"Mute gain":L"Restore gain");
            return 0;
        }
        if(view && message==WM_TIMER) {
            SendMessageW(window,WM_COMMAND,1,0);KillTimer(window,1);
            PostMessageW(GetParent(window),WM_CLOSE,0,0);return 0;
        }
        return DefWindowProcW(window,message,first,second);
    }
public:
    explicit FixtureView(EditController* owner) : controller(owner) { rect=ViewRect(0,0,400,150); }
    tresult PLUGIN_API isPlatformTypeSupported(FIDString type) override {
        return strcmp(type,kPlatformTypeHWND)==0?kResultTrue:kResultFalse;
    }
    tresult PLUGIN_API attached(void* parent,FIDString type) override {
        if(isPlatformTypeSupported(type)!=kResultTrue) return kResultFalse;
        WNDCLASSW kind{};kind.lpfnWndProc=procedure;kind.hInstance=GetModuleHandleW(nullptr);
        kind.lpszClassName=L"ArrangerFixtureView";kind.hbrBackground=reinterpret_cast<HBRUSH>(COLOR_WINDOW+1);
        RegisterClassW(&kind);
        child=CreateWindowW(kind.lpszClassName,L"",WS_CHILD|WS_VISIBLE,0,0,400,150,
                            static_cast<HWND>(parent),nullptr,kind.hInstance,nullptr);
        if(!child)return kResultFalse;
        SetWindowLongPtrW(child,GWLP_USERDATA,reinterpret_cast<LONG_PTR>(this));
        CreateWindowW(L"STATIC",L"Owned VST3 editor fixture · gain parameter",WS_CHILD|WS_VISIBLE,
                       20,20,360,30,child,nullptr,kind.hInstance,nullptr);
        CreateWindowW(L"BUTTON",controller->getParamNormalized(1)>0?L"Mute gain":L"Restore gain",
                       WS_CHILD|WS_VISIBLE|WS_TABSTOP,20,65,180,35,child,reinterpret_cast<HMENU>(1),kind.hInstance,nullptr);
        if(std::getenv("ARRANGER_FIXTURE_EDITOR_AUTOCLOSE")) SetTimer(child,1,200,nullptr);
        return CPluginView::attached(parent,type);
    }
    tresult PLUGIN_API removed() override {
        if(child)DestroyWindow(child);child=nullptr;return CPluginView::removed();
    }
};

class FixtureController : public EditController {
public:
    static FUnknown* create(void*) { return static_cast<IEditController*>(new FixtureController); }
    IPlugView* PLUGIN_API createView(FIDString name) override {
        return strcmp(name,ViewType::kEditor)==0?new FixtureView(this):nullptr;
    }
    tresult PLUGIN_API initialize(FUnknown* context) override {
        auto result=EditController::initialize(context);
        if (result==kResultOk) parameters.addParameter(STR16("Gain"),nullptr,0,1,
            ParameterInfo::kCanAutomate,1);
        return result;
    }
    tresult PLUGIN_API setComponentState(IBStream* stream) override {
        int32 version=0; float gain=0;
        if (stream->read(&version,sizeof(version))!=kResultOk || version!=2 ||
            stream->read(&gain,sizeof(gain))!=kResultOk) return kResultFalse;
        return setParamNormalized(1,gain);
    }
    tresult PLUGIN_API getState(IBStream* stream) override {
        float gain=static_cast<float>(getParamNormalized(1));
        return stream->write(&gain,sizeof(gain));
    }
    tresult PLUGIN_API setState(IBStream* stream) override {
        float gain=0;
        return stream->read(&gain,sizeof(gain))==kResultOk ? setParamNormalized(1,gain) : kResultFalse;
    }
};

BEGIN_FACTORY_DEF("Sample Arranger", "", "")
DEF_CLASS2(INLINE_UID(0x66231001, 0x14424231, 0xA5621002, 0x12142801),
           PClassInfo::kManyInstances, kVstAudioEffectClass, "Arranger Delay Fixture",
           0, "Fx|Delay", "1.0.0", kVstVersionString, DelayFixture::create)
DEF_CLASS2(INLINE_UID(0x66231002, 0x14424231, 0xA5621002, 0x12142801),
           PClassInfo::kManyInstances, kVstComponentControllerClass, "Delay Controller",
           0, "", "1.0.0", kVstVersionString, FixtureController::create)
DEF_CLASS2(INLINE_UID(0x66231003, 0x14424231, 0xA5621002, 0x12142801),
           PClassInfo::kManyInstances, kVstAudioEffectClass, "Delayed Instrument Fixture",
           0, "Instrument|Synth", "1.0.0", kVstVersionString, DelayFixture::synth)
DEF_CLASS2(INLINE_UID(0x66231004, 0x14424231, 0xA5621002, 0x12142801),
           PClassInfo::kManyInstances,kVstAudioEffectClass,"Sidechain Multi-output Fixture",
           0,"Fx|Tools","1.0.0",kVstVersionString,DelayFixture::routed)
  DEF_CLASS2(INLINE_UID(0x66231005,0x14424231,0xA5621002,0x12142801),
             PClassInfo::kManyInstances,kVstAudioEffectClass,"Fixed Mono Delay Fixture",
             0,"Fx|Delay","1.0.0",kVstVersionString,DelayFixture::monoEffect)
  DEF_CLASS2(INLINE_UID(0x66231006,0x14424231,0xA5621002,0x12142801),
             PClassInfo::kManyInstances,kVstAudioEffectClass,"Fixed Mono Instrument Fixture",
             0,"Instrument|Synth","1.0.0",kVstVersionString,DelayFixture::monoSynth)
  END_FACTORY
