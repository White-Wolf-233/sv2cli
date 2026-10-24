// SPDX-License-Identifier: AGPL-3.0-or-later
// Public JUCE/VST3 host. No proprietary engine code is inspected or patched.
#include <juce_audio_processors/juce_audio_processors.h>
#include <juce_audio_formats/juce_audio_formats.h>
#include <mutex>
#include <stdexcept>
#include <cmath>

#if defined(_WIN32)
 #define SV_EXPORT extern "C" __declspec(dllexport)
#else
 #define SV_EXPORT extern "C" __attribute__((visibility("default")))
#endif
using Callback = int (*)(const char*);

namespace {
struct Tempo { int64_t sample; double quarter, bpm; };
struct Meter { int64_t sample; double quarter; int index, numerator, denominator; };

class SampleClock final : public juce::AudioPlayHead {
public:
    explicit SampleClock(double sr) : rate(sr) {}
    std::vector<Tempo> tempos;
    std::vector<Meter> meters;
    void set(int64_t sample, bool playing) {
        std::lock_guard<std::mutex> lock(mutex);
        size_t ti=0,mi=0;
        while(ti+1<tempos.size() && tempos[ti+1].sample<=sample)++ti;
        while(mi+1<meters.size() && meters[mi+1].sample<=sample)++mi;
        const auto& t=tempos.at(ti);const auto& m=meters.at(mi);
        const double q=t.quarter+(sample-t.sample)/rate*t.bpm/60.0;
        const double barLength=m.numerator*4.0/m.denominator;
        const auto bars=static_cast<int64_t>(std::floor((q-m.quarter)/barLength+1e-10));
        pos.setTimeInSamples(sample);pos.setTimeInSeconds(sample/rate);
        pos.setPpqPosition(q);pos.setBpm(t.bpm);
        pos.setIsPlaying(playing);pos.setIsRecording(false);pos.setIsLooping(false);
        pos.setTimeSignature(TimeSignature{m.numerator,m.denominator});
        pos.setBarCount(m.index+bars);pos.setPpqPositionOfLastBarStart(m.quarter+bars*barLength);
        // No invented system-time timestamp. Offline sample time is authoritative.
    }
    juce::Optional<PositionInfo> getPosition() const override {
        std::lock_guard<std::mutex> lock(mutex);return pos;
    }
    int nextBlock(int64_t sample,int wanted) const {
        for(const auto& t:tempos)if(t.sample>sample && t.sample<sample+wanted)wanted=static_cast<int>(t.sample-sample);
        for(const auto& m:meters)if(m.sample>sample && m.sample<sample+wanted)wanted=static_cast<int>(m.sample-sample);
        return wanted;
    }
private:
    double rate;mutable std::mutex mutex;PositionInfo pos;
};

// Some plugins commit component state when their controller view is attached.
// The initialization window stays hidden and is destroyed before playback.
class InitialEditor final : public juce::DocumentWindow {
public:
    explicit InitialEditor(juce::AudioProcessor& p)
      : DocumentWindow("sv2cli initialization",juce::Colours::black,0) {
        setUsingNativeTitleBar(true);
        auto* editor=p.createEditorIfNeeded();
        if(!editor)throw std::runtime_error("Plugin editor initialization failed");
        setContentOwned(editor,true);
    }
    void closeButtonPressed() override {}
};

void saveState(juce::AudioPluginInstance& plugin,const juce::File& file) {
    juce::MemoryBlock state;plugin.getStateInformation(state);
    if(!file.replaceWithData(state.getData(),state.getSize()))throw std::runtime_error("Cannot save plugin state");
}

void render(const juce::var& job,Callback callback) {
    auto get=[&](const char* key){return job.getProperty(key,{});};
    auto emit=[&](const char* kind,juce::DynamicObject::Ptr object=nullptr) {
        if(!object)object=new juce::DynamicObject();object->setProperty("event",kind);
        auto text=juce::JSON::toString(juce::var(object.get()),true);
        if(callback(text.toRawUTF8())!=0)throw std::runtime_error("Host callback rejected operation");
    };
    const double rate=get("sampleRate"),duration=get("duration"),warmup=get("warmupSeconds");
    const int block=get("bufferSize"),channels=get("channels"),bits=get("bitDepth");
    if(!std::isfinite(rate)||!std::isfinite(duration)||!std::isfinite(warmup)||rate<=0||duration<=0||warmup<0
       ||block<16||block>8192||(channels!=1&&channels!=2)||(bits!=16&&bits!=24))throw std::runtime_error("Invalid native render settings");
    const int64_t frames=static_cast<int64_t>(std::llround(rate*duration));
    if(frames<=0)throw std::runtime_error("Empty render");
    SampleClock clock(rate);
    const auto tempoValue=get("tempoSegments"),meterValue=get("meterSegments");
    if(auto* list=tempoValue.getArray())for(const auto& r:*list)
        clock.tempos.push_back({static_cast<int64_t>(r["sample"]),static_cast<double>(r["quarter"]),static_cast<double>(r["bpm"])});
    if(auto* list=meterValue.getArray())for(const auto& r:*list)
        clock.meters.push_back({static_cast<int64_t>(r["sample"]),static_cast<double>(r["quarter"]),static_cast<int>(r["index"]),static_cast<int>(r["numerator"]),static_cast<int>(r["denominator"])});
    if(clock.tempos.empty()||clock.meters.empty()||clock.tempos.front().sample!=0||clock.meters.front().sample!=0)
        throw std::runtime_error("Clock maps must start at sample zero");
    for(size_t i=0;i<clock.tempos.size();++i)if(!std::isfinite(clock.tempos[i].bpm)||clock.tempos[i].bpm<=0
       ||(i&&clock.tempos[i].sample<=clock.tempos[i-1].sample))throw std::runtime_error("Invalid tempo map");
    for(size_t i=0;i<clock.meters.size();++i)if(clock.meters[i].numerator<=0||clock.meters[i].denominator<=0
       ||(i&&clock.meters[i].sample<=clock.meters[i-1].sample))throw std::runtime_error("Invalid meter map");
    clock.set(0,false);
    auto work=juce::File(get("work").toString());if(!work.isDirectory())throw std::runtime_error("Work directory missing");
    juce::AudioPluginFormatManager formats;formats.addDefaultFormats();
    juce::OwnedArray<juce::PluginDescription> descriptions;
    for(int i=0;i<formats.getNumFormats();++i)if(formats.getFormat(i)->getName()=="VST3")
        formats.getFormat(i)->findAllTypesForFile(descriptions,get("plugin").toString());
    if(descriptions.size()!=1)throw std::runtime_error("Expected exactly one VST3 instrument");
    emit("loading_plugin");juce::String error;
    auto plugin=formats.createPluginInstance(*descriptions[0],rate,block,error);
    if(!plugin)throw std::runtime_error(error.toStdString());
    plugin->setPlayHead(&clock);plugin->setNonRealtime(true);
    saveState(*plugin,work.getChildFile("native-base-state.bin"));
    emit("native_state_required");
    juce::MemoryBlock state;
    if(!work.getChildFile("native-project-state.bin").loadFileAsData(state))throw std::runtime_error("Patched state missing");
    plugin->setStateInformation(state.getData(),static_cast<int>(state.getSize()));
    {InitialEditor editor(*plugin);}
    plugin->prepareToPlay(rate,block);
    emit("warming_up");
    const double deadline=juce::Time::getMillisecondCounterHiRes()+warmup*1000.0;
    while(juce::Time::getMillisecondCounterHiRes()<deadline)
        juce::MessageManager::getInstance()->runDispatchLoopUntil(10);
    saveState(*plugin,work.getChildFile("loaded-state.bin"));emit("native_loaded_score_ready");
    const int nativeChannels=plugin->getTotalNumOutputChannels();
    if(nativeChannels<2)throw std::runtime_error("Plugin main stereo bus unavailable");
    auto info=new juce::DynamicObject();info->setProperty("latencySamples",plugin->getLatencySamples());
    info->setProperty("renderPasses",1);info->setProperty("frames",static_cast<juce::int64>(frames));emit("native_single_pass",info);
    auto output=work.getChildFile("render.wav");
    if(output.exists())throw std::runtime_error("Raw output already exists");
    auto stream=output.createOutputStream();juce::WavAudioFormat format;
    std::unique_ptr<juce::AudioFormatWriter> writer(format.createWriterFor(stream.get(),rate,channels,bits,{},0));
    if(!writer)throw std::runtime_error("Cannot create WAV writer");stream.release();
    juce::AudioBuffer<float> audio(nativeChannels,block),stereo(channels,block);juce::MidiBuffer midi;
    plugin->reset();clock.set(0,true);
    int64_t nextProgress=static_cast<int64_t>(rate*5);
    for(int64_t sample=0;sample<frames;) {
        const int n=clock.nextBlock(sample,static_cast<int>(std::min<int64_t>(block,frames-sample)));
        audio.setSize(nativeChannels,n,false,false,true);stereo.setSize(channels,n,false,false,true);
        audio.clear();midi.clear();clock.set(sample,true);
        plugin->processBlock(audio,midi);
        if(channels==2)for(int c=0;c<2;++c)stereo.copyFrom(c,0,audio,c,0,n);
        else {stereo.copyFrom(0,0,audio.getReadPointer(0),n,.5f);stereo.addFrom(0,0,audio.getReadPointer(1),n,.5f);}
        // Validate the floating-point output before integer PCM could conceal
        // a NaN or saturate an over-range sample.
        for(int c=0;c<channels;++c)for(int i=0;i<n;++i) {
            const auto value=stereo.getSample(c,i);
            if(!std::isfinite(value))throw std::runtime_error("Plugin returned non-finite audio");
            if(std::abs(value)>=1.0f)throw std::runtime_error("Plugin output clips; reduce track gain before exporting");
        }
        if(!writer->writeFromAudioSampleBuffer(stereo,0,n))throw std::runtime_error("WAV write failed");
        // The position remains immutable while plugin messages are dispatched.
        // There is no racing graph renderer, retry, measured shift or time warp.
        juce::MessageManager::getInstance()->runDispatchLoopUntil(1);
        sample+=n;
        if(sample>=nextProgress) {auto p=new juce::DynamicObject();p->setProperty("renderedFrames",static_cast<juce::int64>(sample));emit("native_render_progress",p);nextProgress+=static_cast<int64_t>(rate*5);}
    }
    writer.reset();clock.set(frames,false);audio.clear();midi.clear();plugin->processBlock(audio,midi);
    plugin->releaseResources();emit("native_render_complete");
}
}

SV_EXPORT int sv2cli_transport_abi_version() {return 1;}
SV_EXPORT int sv2cli_transport_render(const char* json,Callback callback) {
    try {
        if(!json||!callback)return 1;
        juce::ScopedJuceInitialiser_GUI gui;
        render(juce::JSON::parse(juce::String::fromUTF8(json)),callback);return 0;
    } catch(const std::exception& e) {
        if(callback) {auto p=new juce::DynamicObject();p->setProperty("event","native_error");p->setProperty("message",juce::String::fromUTF8(e.what()));callback(juce::JSON::toString(juce::var(p),true).toRawUTF8());}
        return 1;
    }
}
