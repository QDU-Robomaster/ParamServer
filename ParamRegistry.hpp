#pragma once

#include <netinet/in.h>
#include <sys/socket.h>
#include <unistd.h>

#include <memory>

#include "ParamBus.hpp"
#include "thread.hpp"

class ParamRegistry
{
 public:
  static ParamRegistry& Get()
  {
    static ParamRegistry g;
    return g;
  }

  // 注册模块（第一次注册时自动启动服务器）
  void Register(const char* name, void* inst, CommandFun func, uint16_t port = 5555)
  {
    if (!name || !func || !inst)
    {
      return;
    }

    auto m = std::make_unique<ModuleParams>(name, inst, func);
    ModuleParams* raw = m.get();
    modules_.push_back(std::move(m));
    bus_.Register(raw);

    if (!started_)
    {
      port_ = port;  // 只在第一次注册时记录端口
      StartServer();
      started_ = true;
    }
  }

  ParamBus& Bus() { return bus_; }

  // 线程入口，简单的行协议 TCP server
  static void ServerMain(ParamBus* bus)
  {
    if (!bus)
    {
      return;
    }

    auto& reg = ParamRegistry::Get();
    uint16_t port = reg.port_;

    int s = socket(AF_INET, SOCK_STREAM, 0);
    if (s < 0)
    {
      XR_LOG_ERROR("ParamServer: socket failed: %s", strerror(errno));
      return;
    }

    int opt = 1;
    setsockopt(s, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt));

    sockaddr_in addr{};
    addr.sin_family = AF_INET;
    addr.sin_addr.s_addr = htonl(INADDR_LOOPBACK);  // 127.0.0.1
    addr.sin_port = htons(port);

    if (bind(s, reinterpret_cast<sockaddr*>(&addr), sizeof(addr)) < 0)
    {
      XR_LOG_ERROR("ParamServer: bind failed: %s", strerror(errno));
      close(s);
      return;
    }

    if (listen(s, 4) < 0)
    {
      XR_LOG_ERROR("ParamServer: listen failed: %s", strerror(errno));
      close(s);
      return;
    }

    XR_LOG_INFO("ParamServer: listening on 127.0.0.1:%d", port);

    while (true)
    {
      int c = accept(s, nullptr, nullptr);
      if (c < 0)
      {
        XR_LOG_ERROR("ParamServer: accept failed: %s", strerror(errno));
        break;
      }

      std::string line;
      char buf[256];

      while (true)
      {
        size_t n = read(c, buf, sizeof(buf));
        if (n <= 0)
        {
          break;
        }

        for (size_t i = 0; i < n; ++i)
        {
          char ch = buf[i];
          if (ch == '\n')
          {
            if (!line.empty())
            {
              bus->EvalLine(line);
              line.clear();
            }
          }
          else if (ch != '\r')
          {
            line.push_back(ch);
          }
        }
      }

      close(c);
    }

    close(s);
  }

  void StartServer()
  {
    XR_LOG_INFO("ParamServer: starting thread");
    thread_.Create(&bus_, &ParamRegistry::ServerMain, "ParamServer", 81920,
                   LibXR::Thread::Priority::MEDIUM);
  }

 private:
  ParamBus bus_;
  uint16_t port_{5555};
  std::vector<std::unique_ptr<ModuleParams>> modules_;
  LibXR::Thread thread_;
  bool started_{};
};
