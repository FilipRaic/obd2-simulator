cmake_minimum_required(VERSION 3.16)
project(obd2_simulator CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

add_library(sim_core
    src/pid_encoder.cpp
    src/iso_tp.cpp
    src/can_handler.cpp
    src/simulator_core.cpp
)
target_include_directories(sim_core PUBLIC include)

# Host-side unit tests (no ESP32 hardware needed)
enable_testing()
add_executable(sim_test tests/test_simulator.cpp)
target_link_libraries(sim_test sim_core)
add_test(NAME sim_test COMMAND sim_test)
