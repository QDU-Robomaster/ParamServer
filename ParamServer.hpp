#pragma once

// clang-format off
/* === MODULE MANIFEST V2 ===
module_description: No description provided
constructor_args:
  - name: "armor_detector"
  - inst: ArmorDetector_0
  - func: ArmorDetector::CommandAdapter
  - port: 5555
template_args: []
required_hardware: []
depends:
  - qdu-future/CameraBase
=== END MANIFEST === */
// clang-format on

#include "ParamRegistry.hpp"
#include "app_framework.hpp"

class ParamServer : public LibXR::Application
{
 public:
  template <typename T>
  ParamServer(LibXR::HardwareContainer&, LibXR::ApplicationManager&, const char* name,
              T& inst, CommandFun func, uint16_t port = 5555)
  {
    ParamRegistry::Get().Register(name, static_cast<void*>(&inst), func, port);
  }

  void OnMonitor() override {}

 private:
};