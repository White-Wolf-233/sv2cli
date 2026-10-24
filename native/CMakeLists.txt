cmake_minimum_required(VERSION 3.22)
project(sv2cli_transport VERSION 1.0 LANGUAGES C CXX)
set(CMAKE_CXX_STANDARD 17)
set(JUCE_MODULES_ONLY ON CACHE BOOL "" FORCE)
if(NOT TARGET juce::juce_audio_processors)
    if(SV2CLI_JUCE_DIR)
        add_subdirectory("${SV2CLI_JUCE_DIR}" JUCE)
    else()
        include(FetchContent)
        FetchContent_Declare(JUCE GIT_REPOSITORY https://github.com/juce-framework/JUCE.git
            GIT_TAG 51a8a6d7aeae7326956d747737ccf1575e61e209 GIT_SHALLOW FALSE)
        FetchContent_MakeAvailable(JUCE)
    endif()
endif()
add_library(sv2cli_transport SHARED transport.cpp)
target_compile_definitions(sv2cli_transport PRIVATE
    JUCE_PLUGINHOST_VST3=1 JUCE_PLUGINHOST_VST=0 JUCE_PLUGINHOST_AU=0
    JUCE_WEB_BROWSER=0 JUCE_USE_CURL=0 JUCE_MODAL_LOOPS_PERMITTED=1
    JUCE_GLOBAL_MODULE_SETTINGS_INCLUDED=1 JUCE_STANDALONE_APPLICATION=1)
target_link_libraries(sv2cli_transport PRIVATE juce::juce_audio_processors juce::juce_audio_formats)
