#pragma once

#include <sstream>
#include <string>
#include <unordered_map>
#include <vector>

typedef int (*CommandFun)(void* instance, int argc, char** argv);
class ModuleParams
{
 public:
  ModuleParams(const char* name, void* inst, CommandFun f)
      : name_(name), inst_(inst), func_(f)
  {
  }
  virtual ~ModuleParams() = default;
  const char* Name() const { return name_; }

  int EvalCommand(int argc, char** argv)
  {
    if (!func_ || !inst_)
    {
      return -1;
    }
    return func_(inst_, argc, argv);
  }

 private:
  const char* name_;
  void* inst_;
  CommandFun func_;
};

class ParamBus
{
 public:
  void Register(ModuleParams* mod)
  {
    if (!mod || !mod->Name())
    {
      return;
    }
    modules_[mod->Name()] = mod;
  }

  int EvalLine(const std::string& line)
  {
    std::istringstream iss(line);
    std::vector<std::string> tokens;
    std::string tok;
    while (iss >> tok)
    {
      tokens.push_back(tok);
    }
    if (tokens.empty())
    {
      return -1;
    }

    auto it = modules_.find(tokens[0]);
    if (it == modules_.end())
    {
      return -1;
    }
    // argv[0]=模块名, argv[1]=命令, argv[2]=参数
    std::vector<char*> argv;
    argv.reserve(tokens.size());
    for (auto& s : tokens)
    {
      argv.push_back(&s[0]);
    }
    return it->second->EvalCommand(static_cast<int>(argv.size()), argv.data());
  }

 private:
  std::unordered_map<std::string, ModuleParams*> modules_;
};
