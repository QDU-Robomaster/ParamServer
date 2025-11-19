# ParamServer 模块

## 模块简介

---

这是一个基于 TCP/IP 协议和 YAML 配置驱动的参数调试系统。它实现了 Python GUI 前端与 C++ 上位机后端的解耦，支持参数的实时热调整、持久化保存以及线程安全的参数更新。

Python 客户端会读取 xrobot.yaml 中的 cfg 结构，递归生成对应的参数调节面板，修改参数后指令通过 TCP 发送至 C++ 服务端，同时支持将调整好的参数写回 xrobot.yaml 。

## 运行环境

---

- Python: Python3.x, PyQt5, pyyaml
- C++: LibXR

## 构造参数

---

`ParamServer<tpename T>` 类的构造参数如下：

- `hw`: `LibXR::HardwareContainer&`，硬件容器的引用。
- `app`: `LibXR::ApplicationManager&`，应用管理器的引用。
- `name`: `const char*`，模块参数服务器注册名
- `inst`: `T&`，模块实例的引用
- `func`: `CommandFun`，命令回调函数
- `port`: `uint16_t`，TCP 服务监听端口，在第一次注册时生效

## 如何使用

---

```bash
# 添加需要管理参数的模块实例
xrobot_add_mod Module
# 添加 ParamServer 模块实例
xrobot_add_mod ParamServer

# 修改 xrobot.yaml 中 ParamServer 实例的参数

# 生成主程序入口
xrobot_gen_main
```

## 如何为新模块添加调参功能

---

1. C++ 模块实现

   在模块中定义配置结构体，并实现命令回调函数，使用缓存与脏标记保证线程安全。

   示例：

   ```c++
   // Module.hpp
   class Module : public LibXR::Application
   {
    public:
     // 1. 定义嵌套配置结构 (对应 YAML)
     struct Config
     {
       struct ParamStruct1
       {
         double param_1;
         double param_2;
       } param_struct_1;
       float param_3;
     };
   
     Module(LibXR::HardwareContainer& hw, LibXR::ApplicationManager& mgr, Config cfg,
            const char* name);
   
     // 2. 声明命令处理函数
     static int CommandFun(Module* self, int argc, char** argv);
     static int CommandAdapter(void* instance, int argc, char** argv)
     {
       return CommandFun(static_cast<Module*>(instance), argc, argv);
     }
   
    private:
     void SetConfig(const Config& cfg);            // 应用参数的内部函数
     const char* name_{};                          // 命令头
     LibXR::RamFS::File cmd_file_;                 // 内存文件系统命令文件
     std::atomic<bool> params_is_changed_{false};  // 脏标记
     Config cfg_cache_;                            // 参数缓存
   };
   ```

   ```c++
   // Module.cpp
   // 构造函数
   Module::Module(LibXR::HardwareContainer& hw, LibXR::ApplicationManager& mgr, Config cfg,
                  const char* name)
       : name_(name),
         cfg_cache_(cfg),
         cmd_file_(LibXR::RamFS::CreateFile(name, CommandFun, this)) // 创建可执行文件
   {
     hw.template FindOrExit<LibXR::RamFS>({"ramfs"})->Add(
         cmd_file_);  // 将可执行文件添加到内存文件系统中
   }
   
   // 业务循环或回调
   void Module::Callback()
   {
     // 3. 在每一帧开始时检查并更新参数，确保线程安全
     if (params_changed_)
     {
       SetConfig(cfg_cache_);
       params_changed_ = false;
     }
     // ... 执行业务逻辑
   }
   
   // 4. 实现命令解析
   int Module::CommandFun(Module* self, int argc, char** argv)
   {
     if (argc == 2 && std::string(argv[1]) == "show")
     {
       // 打印当前参数
       LibXR::STDIO::Printf("speed_kp: %f\n", self->cfg_cache_.motor.speed_kp);
       return 0;
     }
   
     if (argc == 3)
     {
       std::string cmd = argv[1];
       std::string val = argv[2];
   
       // ... 根据命令修改参数
   
       return 0;
     }
     return -1;
   }
   ```

2. xrobot.yaml 配置

   在 `xrobot.yaml`中实例化并注册参数服务，GUI 前端会自动解析这里的 `cfg` 结构并生成界面

   ```yaml
   modules:
     # 1. 实例化业务模块
     - id: Module_0
       name: Module
       constructor_args:
         cfg:
           param_struct_1:
             param_1: 0.5
             param_2: 0.01
           param_3: 0.2
   
     # 2. 注册参数服务 (ParamServer)
     # 这将模块实例与 TCP 指令系统绑定
     - id: ParamServer_Module
       name: ParamServer
       constructor_args:
         name: module # 通信名称 (GUI 发送指令的前缀)
         instance: "@Module_0" # 指向上面定义的模块 ID
         command_adapter: Module::CommandAdapter # 指定 C++ 静态回调
   ```

3. `GUI.py` 会自动解析 `xrobot.yaml` ，GUI 在启动时会自动发现 `Module_0` 模块及其配置，生成对应的 "Module" 选项卡，并根据 YAML 层级结构生成参数。当点击 Apply 时，会自动发送形如 `module param_1 1.0` 的指令。

   注意：服务端与客户端参数键名必须一致。
