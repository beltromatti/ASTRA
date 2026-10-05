// Compiles an HLSL file with the DXC library the engine ships (so the Custom-node shaders of the war's effects can be checked for syntax and types
// without the editor): dxc_check <file.hlsl> [entry main] [profile ps_6_0]. Prints the compiler's messages; exit 0 when it compiled.
//
//   clang++ -std=c++17 -fms-extensions -Wno-everything -I"<UE>/Engine/Source/ThirdParty/ShaderConductor/ShaderConductor/External/DirectXShaderCompiler/include" \
//       tools/art/dxc_check.cpp -o /tmp/dxc_check -ldl
#include <dlfcn.h>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <sstream>
#include <string>
#include <vector>

#include "dxc/WinAdapter.h"
#include "dxc/dxcapi.h"

int main(int argc, char** argv)
{
	if (argc < 2)
	{
		fprintf(stderr, "usage: dxc_check file.hlsl [entry] [profile]\n");
		return 2;
	}
	const char* Lib = getenv("DXC_LIB") ? getenv("DXC_LIB") : "/Users/Shared/Epic Games/UE_5.8/Engine/Binaries/ThirdParty/ShaderConductor/Mac/libdxcompiler.dylib";
	void* H = dlopen(Lib, RTLD_NOW);
	if (!H)
	{
		fprintf(stderr, "cannot load %s: %s\n", Lib, dlerror());
		return 3;
	}
	typedef HRESULT (*CreateFn)(REFCLSID, REFIID, LPVOID*);
	CreateFn Create = (CreateFn)dlsym(H, "DxcCreateInstance");
	if (!Create)
	{
		fprintf(stderr, "no DxcCreateInstance\n");
		return 3;
	}
	std::ifstream In(argv[1]);
	std::stringstream Ss;
	Ss << In.rdbuf();
	const std::string Src = Ss.str();
	const std::string Entry = argc > 2 ? argv[2] : "main";
	const std::string Profile = argc > 3 ? argv[3] : "ps_6_0";
	IDxcUtils* Utils = nullptr;
	IDxcCompiler3* Comp = nullptr;
	if (FAILED(Create(CLSID_DxcUtils, __uuidof(IDxcUtils), (void**)&Utils)) || FAILED(Create(CLSID_DxcCompiler, __uuidof(IDxcCompiler3), (void**)&Comp)))
	{
		fprintf(stderr, "cannot create the compiler\n");
		return 3;
	}
	DxcBuffer Buf;
	Buf.Ptr = Src.data();
	Buf.Size = Src.size();
	Buf.Encoding = DXC_CP_UTF8;
	std::vector<std::wstring> Args = {L"-E", std::wstring(Entry.begin(), Entry.end()), L"-T", std::wstring(Profile.begin(), Profile.end()), L"-HV", L"2021"};
	const bool bStats = getenv("DXC_STATS") != nullptr;                      // DXC_STATS=1: also print the size of the compiled shader (a rough proxy for what a pixel of it costs)
	std::vector<LPCWSTR> Raw;
	for (const std::wstring& A : Args)
	{
		Raw.push_back(A.c_str());
	}
	IDxcResult* Res = nullptr;
	HRESULT Hr = Comp->Compile(&Buf, Raw.data(), (UINT32)Raw.size(), nullptr, __uuidof(IDxcResult), (void**)&Res);
	if (FAILED(Hr) || !Res)
	{
		fprintf(stderr, "compile call failed\n");
		return 4;
	}
	IDxcBlobUtf8* Err = nullptr;
	Res->GetOutput(DXC_OUT_ERRORS, __uuidof(IDxcBlobUtf8), (void**)&Err, nullptr);
	if (Err && Err->GetStringLength() > 0)
	{
		fputs(Err->GetStringPointer(), stdout);
	}
	HRESULT Status = 0;
	Res->GetStatus(&Status);
	if (FAILED(Status))
	{
		printf("COMPILE FAILED\n");
		return 1;
	}
	if (bStats)
	{
		// instructions of the entry point as the disassembly lists them: the ones that assign a value or call an op; texture reads and the transcendental ops (sin, cos, exp, log, sqrt, rsqrt...) apart
		IDxcBlob* Obj = nullptr;
		Res->GetOutput(DXC_OUT_OBJECT, __uuidof(IDxcBlob), (void**)&Obj, nullptr);
		IDxcResult* DisRes = nullptr;
		IDxcBlobUtf8* Dis = nullptr;
		if (Obj)
		{
			DxcBuffer ObjBuf;
			ObjBuf.Ptr = Obj->GetBufferPointer();
			ObjBuf.Size = Obj->GetBufferSize();
			ObjBuf.Encoding = 0;
			if (SUCCEEDED(Comp->Disassemble(&ObjBuf, __uuidof(IDxcResult), (void**)&DisRes)) && DisRes)
			{
				DisRes->GetOutput(DXC_OUT_DISASSEMBLY, __uuidof(IDxcBlobUtf8), (void**)&Dis, nullptr);
			}
		}
		if (Dis && Dis->GetStringLength() > 0)
		{
			std::istringstream Lines(Dis->GetStringPointer());
			std::string L;
			int Instr = 0, Tex = 0, Unary = 0;
			bool bBody = false;
			while (std::getline(Lines, L))
			{
				if (L.rfind("define ", 0) == 0)
				{
					bBody = true;
					continue;
				}
				if (!bBody)
				{
					continue;
				}
				if (!L.empty() && L[0] == '}')
				{
					bBody = false;
					continue;
				}
				if (L.size() > 2 && L[0] == ' ' && L[1] == ' ' && (L[2] == '%' || L.compare(2, 4, "call") == 0 || L.compare(2, 2, "br") == 0 || L.compare(2, 3, "ret") == 0))
				{
					++Instr;
					Tex += (L.find("dx.op.sample") != std::string::npos || L.find("dx.op.textureLoad") != std::string::npos) ? 1 : 0;
					Unary += L.find("dx.op.unary") != std::string::npos ? 1 : 0;
				}
			}
			printf("STATS instructions=%d texture=%d unary=%d\n", Instr, Tex, Unary);
		}
	}
	printf("COMPILED\n");
	return 0;
}
