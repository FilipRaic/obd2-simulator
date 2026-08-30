# Compiles the portable protocol core (../include, ../src) into the firmware
# build, so the same sources serve the CMake host tests and every PlatformIO
# environment without duplication.
import os

Import("env")

core_dir = os.path.normpath(os.path.join(env.subst("$PROJECT_DIR"), ".."))
env.Append(CPPPATH=[os.path.join(core_dir, "include")])
env.BuildSources(os.path.join("$BUILD_DIR", "sim_core"),
                 os.path.join(core_dir, "src"))
