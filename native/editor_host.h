// Isolated Windows native editor lifecycle. No editor code runs in the desktop.
#include "pluginterfaces/gui/iplugview.h"
#include <atomic>
#include <map>

class EditorHost final : public IPlugFrame, public IComponentHandler {
    std::atomic<uint32> references{1};
public:
    HWND window=nullptr;
    IPlugView* view=nullptr;
    IEditController* controller=nullptr;
    std::map<ParamID,ParamValue> edits;
    bool restartRequested=false;
    tresult PLUGIN_API queryInterface(const TUID iid,void** object) override {
        if (FUnknownPrivate::iidEqual(iid,IPlugFrame::iid) || FUnknownPrivate::iidEqual(iid,FUnknown::iid))
            *object=static_cast<IPlugFrame*>(this);
        else if (FUnknownPrivate::iidEqual(iid,IComponentHandler::iid)) *object=static_cast<IComponentHandler*>(this);
        else { *object=nullptr; return kNoInterface; }
        addRef(); return kResultOk;
    }
    uint32 PLUGIN_API addRef() override { return ++references; }
    uint32 PLUGIN_API release() override { auto count=--references; if(!count) delete this; return count; }
    tresult PLUGIN_API resizeView(IPlugView* incoming,ViewRect* rect) override {
        if (!window || incoming!=view || !rect || rect->getWidth()<100 || rect->getHeight()<60 ||
            rect->getWidth()>8192 || rect->getHeight()>8192) return kInvalidArgument;
        RECT outer{0,0,rect->getWidth(),rect->getHeight()};
        AdjustWindowRect(&outer,static_cast<DWORD>(GetWindowLongPtr(window,GWL_STYLE)),FALSE);
        SetWindowPos(window,nullptr,0,0,outer.right-outer.left,outer.bottom-outer.top,SWP_NOMOVE|SWP_NOZORDER);
        return view->onSize(rect);
    }
    tresult PLUGIN_API beginEdit(ParamID) override { return kResultOk; }
    tresult PLUGIN_API performEdit(ParamID id,ParamValue value) override {
        if (!std::isfinite(value) || value<0 || value>1 || edits.size()>=8192) return kInvalidArgument;
        edits[id]=value;
        return controller->setParamNormalized(id,value);
    }
    tresult PLUGIN_API endEdit(ParamID) override { return kResultOk; }
    tresult PLUGIN_API restartComponent(int32) override { restartRequested=true; return kNotImplemented; }
    static LRESULT CALLBACK procedure(HWND window,UINT message,WPARAM first,LPARAM second) {
        auto* host=reinterpret_cast<EditorHost*>(GetWindowLongPtr(window,GWLP_USERDATA));
        if (host && host->view) {
            if (message==WM_SETFOCUS || message==WM_KILLFOCUS) host->view->onFocus(message==WM_SETFOCUS);
            if (message==WM_SIZE && host->view->canResize()==kResultTrue) {
                ViewRect rect{0,0,LOWORD(second),HIWORD(second)};
                host->view->checkSizeConstraint(&rect); host->view->onSize(&rect);
            }
            if (message==WM_MOUSEWHEEL && host->view->onWheel(GET_WHEEL_DELTA_WPARAM(first)/120.0f)==kResultTrue) return 0;
        }
        if (message==WM_CLOSE) { PostQuitMessage(0); return 0; }
        return DefWindowProcW(window,message,first,second);
    }
};

static void editPlugin(IComponent* component,IAudioProcessor* processor,IEditController* controller,
                       const std::map<ParamID,ParamValue>& initial,bool showEditor=true) {
    require(controller && processor,"native editor requires component/controller");
    IPtr<EditorHost> host=owned(new EditorHost);
    host->controller=controller;
    std::map<ParamID,bool> programParameters;
    const int parameterCount=controller->getParameterCount();require(parameterCount>=0 && parameterCount<=8192,"editor parameter count exceeds bound");
    for(int i=0;i<parameterCount;++i) {ParameterInfo parameter{};require(controller->getParameterInfo(i,parameter)==kResultOk,"invalid editor parameter metadata");programParameters[parameter.id]=(parameter.flags&ParameterInfo::kIsProgramChange)!=0;}
    // A program loads many values. Apply it before explicit overrides, regardless
    // of numeric parameter-ID ordering, in both controller and processor.
    for(int phase=0;phase<2;++phase)
        for(const auto& edit:initial) if(programParameters[edit.first]==(phase==0))require(host->performEdit(edit.first,edit.second)==kResultOk,"initial editor edit rejected");
    if(showEditor) {
    IPtr<IPlugView> view=owned(controller->createView(ViewType::kEditor));
    require(view && view->isPlatformTypeSupported(kPlatformTypeHWND)==kResultTrue,
            "plugin has no supported HWND editor; use generic parameters");
    host->view=view;
    require(controller->setComponentHandler(host)==kResultOk,"editor handler rejected");
    WNDCLASSW type{}; type.lpfnWndProc=EditorHost::procedure;
    type.hInstance=GetModuleHandleW(nullptr); type.lpszClassName=L"ArrangerIsolatedEditor";
    type.hCursor=LoadCursor(nullptr,IDC_ARROW); RegisterClassW(&type);
    ViewRect rect{};
    require(view->getSize(&rect)==kResultOk,"editor size unavailable");
    DWORD flags=WS_OVERLAPPEDWINDOW;
    if (view->canResize()!=kResultTrue) flags &= ~(WS_THICKFRAME|WS_MAXIMIZEBOX);
    host->window=CreateWindowW(type.lpszClassName,L"Sample Arranger · Plugin editor",flags,
                              CW_USEDEFAULT,CW_USEDEFAULT,600,400,nullptr,nullptr,type.hInstance,nullptr);
    require(host->window!=nullptr,"editor window creation failed");
    SetWindowLongPtrW(host->window,GWLP_USERDATA,reinterpret_cast<LONG_PTR>(host.get()));
    view->setFrame(host);
    require(host->resizeView(view,&rect)==kResultOk,"editor size rejected");
    require(view->attached(host->window,kPlatformTypeHWND)==kResultOk,"editor attachment failed");
    ShowWindow(host->window,SW_SHOW); UpdateWindow(host->window);
    MSG message{};
    while (GetMessageW(&message,nullptr,0,0)>0) { TranslateMessage(&message); DispatchMessageW(&message); }
    view->removed(); view->setFrame(nullptr); host->view=nullptr;
    DestroyWindow(host->window); controller->setComponentHandler(nullptr);
    }
    require(!host->restartRequested,"plugin requested unsupported editor restart; state not saved");
    if (host->edits.empty()) return;
    // Synchronize exposed controller edits to the processor before capturing state.
    const int inputs=component->getBusCount(kAudio,kInput),outputs=component->getBusCount(kAudio,kOutput);
    require(inputs>=0 && inputs<=2 && outputs>=1 && outputs<=8,"state sync bus count exceeds supported bounds");
    std::array<SpeakerArrangement,2> inputLayouts{};std::array<SpeakerArrangement,8> outputLayouts{};
    std::array<AudioBusBuffers,2> inputBuffers{};std::array<AudioBusBuffers,8> outputBuffers{};
    std::array<std::array<std::array<float,512>,2>,10> silence{};
    std::array<std::array<float*,2>,10> channels{};
    for(int index=0;index<inputs+outputs;++index) {
        const bool incoming=index<inputs;const int bus=incoming?index:index-inputs;BusInfo info{};
        require(component->getBusInfo(kAudio,incoming?kInput:kOutput,bus,info)==kResultOk &&
                (info.channelCount==1 || info.channelCount==2),"state sync buses must be mono/stereo");
        (incoming?inputLayouts[bus]:outputLayouts[bus])=info.channelCount==1?SpeakerArr::kMono:SpeakerArr::kStereo;
        for(int channel=0;channel<2;++channel)channels[index][channel]=silence[index][channel].data();
        auto& buffer=incoming?inputBuffers[bus]:outputBuffers[bus];
        buffer.numChannels=info.channelCount;buffer.channelBuffers32=channels[index].data();
    }
    require(processor->setBusArrangements(inputs?inputLayouts.data():nullptr,inputs,outputLayouts.data(),outputs)==kResultOk,"editor state sync layout rejected");
    ProcessSetup setup{kOffline,kSample32,512,44100.0};
    require(processor->setupProcessing(setup)==kResultOk,"editor state sync setup failed");
    for(int bus=0;bus<inputs;++bus)require(component->activateBus(kAudio,kInput,bus,true)==kResultOk,"state sync input activation failed");
    for(int bus=0;bus<outputs;++bus)require(component->activateBus(kAudio,kOutput,bus,true)==kResultOk,"state sync output activation failed");
    require(component->setActive(true)==kResultOk,"editor state sync activation failed");
    processor->setProcessing(true);
    ProcessData data{};data.processMode=kOffline;data.symbolicSampleSize=kSample32;data.numSamples=512;
    data.numInputs=inputs;data.numOutputs=outputs;data.inputs=inputs?inputBuffers.data():nullptr;data.outputs=outputBuffers.data();
    tresult processed=kResultOk;
    for(int phase=0;phase<2;++phase) {
        ParameterChanges changes(8192);int added=0;
        for(const auto& edit:host->edits) if(programParameters[edit.first]==(phase==0)) {
            const auto value=controller->getParamNormalized(edit.first);require(std::isfinite(value) && value>=0 && value<=1,"invalid final editor parameter");
            int32 index=0;changes.addParameterData(edit.first,index)->addPoint(0,value,index);++added;
        }
        if(!added)continue;
        data.inputParameterChanges=&changes;processed=processor->process(data);if(processed!=kResultOk)break;
    }
    processor->setProcessing(false);component->setActive(false);
    require(processed==kResultOk,"editor changes rejected by processor");
}
