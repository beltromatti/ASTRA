// How long does creating a MTLFXTemporalScaler take (sync vs async init, repeated, different sizes, dynamic res)?
// Build: clang++ -std=c++17 -fobjc-arc -framework Foundation -framework Metal -framework MetalFX probe_create.mm -o /tmp/probe_create
#import <Foundation/Foundation.h>
#import <Metal/Metal.h>
#import <MetalFX/MetalFX.h>

static double Now() { return CFAbsoluteTimeGetCurrent() * 1000.0; }

static const char* UsageString(MTLTextureUsage u, char* buf, size_t n)
{
	buf[0] = 0;
	if (u & MTLTextureUsageShaderRead) strlcat(buf, "Read ", n);
	if (u & MTLTextureUsageShaderWrite) strlcat(buf, "Write ", n);
	if (u & MTLTextureUsageRenderTarget) strlcat(buf, "RenderTarget ", n);
	if (u & MTLTextureUsagePixelFormatView) strlcat(buf, "PixelFormatView ", n);
	return buf;
}

static id<MTLFXTemporalScaler> Make(id<MTLDevice> dev, int iw, int ih, int ow, int oh, bool sync, bool dyn, MTLPixelFormat depthFmt = MTLPixelFormatDepth32Float)
{
	MTLFXTemporalScalerDescriptor* d = [MTLFXTemporalScalerDescriptor new];
	d.colorTextureFormat = MTLPixelFormatRGBA16Float;
	d.depthTextureFormat = depthFmt;
	d.motionTextureFormat = MTLPixelFormatRG16Float;
	d.outputTextureFormat = MTLPixelFormatRGBA16Float;
	d.inputWidth = iw; d.inputHeight = ih;
	d.outputWidth = ow; d.outputHeight = oh;
	d.autoExposureEnabled = NO;
	d.requiresSynchronousInitialization = sync;
	if (dyn)
	{
		d.inputContentPropertiesEnabled = YES;
		d.inputContentMinScale = 1.0f;
		d.inputContentMaxScale = 3.0f;
	}
	return [d newTemporalScalerWithDevice:dev];
}

int main()
{
	@autoreleasepool
	{
		id<MTLDevice> dev = MTLCreateSystemDefaultDevice();
		printf("device: %s  supportsDevice %d  supportsMetal4FX %d  supported content scale [%.2f .. %.2f]\n", dev.name.UTF8String,
			(int)[MTLFXTemporalScalerDescriptor supportsDevice:dev], (int)[MTLFXTemporalScalerDescriptor supportsMetal4FX:dev],
			[MTLFXTemporalScalerDescriptor supportedInputContentMinScaleForDevice:dev], [MTLFXTemporalScalerDescriptor supportedInputContentMaxScaleForDevice:dev]);
		struct Cfg { int iw, ih, ow, oh; bool sync, dyn; const char* label; };
		Cfg cfgs[] = {
			{ 1120, 630, 1600, 900, false, false, "1120x630->1600x900 async" },
			{ 1120, 630, 1600, 900, true,  false, "1120x630->1600x900 sync (repeat)" },
			{ 1120, 630, 1600, 900, true,  true,  "1120x630->1600x900 sync dyn" },
			{ 960, 540, 1600, 900, true, false, "960x540->1600x900 sync" },
			{ 1600, 900, 1600, 900, true, true, "1600x900->1600x900 sync dyn (1:1)" },
			{ 1712, 1112, 1710, 1107, true, true, "1712x1112->1710x1107 sync dyn" },
			{ 1712, 1112, 1710, 1107, true, true, "1712x1112->1710x1107 sync dyn (repeat)" },
			{ 1712, 1112, 1710, 1107, false, true, "1712x1112->1710x1107 async dyn" },
			{ 1600, 900, 1600, 900, true, false, "1600x900->1600x900 sync (1:1 fixed)" },
		};
		for (auto& c : cfgs)
		{
			double t0 = Now();
			id<MTLFXTemporalScaler> s;
			@autoreleasepool { s = Make(dev, c.iw, c.ih, c.ow, c.oh, c.sync, c.dyn); }
			double t1 = Now();
			printf("%-46s : %s  %.1f ms", c.label, s ? "ok " : "FAIL", t1 - t0);
			if (s) printf("  content scale [%.3f .. %.3f]", s.inputContentMinScale, s.inputContentMaxScale);
			printf("\n");
		}
		{
			id<MTLFXTemporalScaler> s = Make(dev, 1600, 900, 1600, 900, true, true);
			char b[128];
			printf("required texture usage: color [%s] depth [%s] motion [%s] reactive [%s] output [%s]\n",
				UsageString(s.colorTextureUsage, b, 128), UsageString(s.depthTextureUsage, b + 0, 128), "", "", "");
			char c[128], d[128], e[128], f[128];
			printf("  color  : %s\n  depth  : %s\n  motion : %s\n  reactive: %s\n  output : %s\n", UsageString(s.colorTextureUsage, c, 128), UsageString(s.depthTextureUsage, d, 128),
				UsageString(s.motionTextureUsage, e, 128), UsageString(s.reactiveTextureUsage, f, 128), UsageString(s.outputTextureUsage, b, 128));
		}
		// Does the depth-stencil format get accepted as a depth input format?
		MTLPixelFormat fmts[] = { MTLPixelFormatDepth32Float, MTLPixelFormatDepth32Float_Stencil8, MTLPixelFormatDepth16Unorm, MTLPixelFormatR32Float, MTLPixelFormatR16Float, MTLPixelFormatX32_Stencil8 };
		const char* names[] = { "Depth32Float", "Depth32Float_Stencil8", "Depth16Unorm", "R32Float", "R16Float", "X32_Stencil8" };
		for (int i = 0; i < 6; ++i)
		{
			id<MTLFXTemporalScaler> s;
			@autoreleasepool { s = Make(dev, 1120, 630, 1600, 900, true, false, fmts[i]); }
			printf("depth format %-24s : %s\n", names[i], s ? "accepted" : "rejected");
		}
	}
	return 0;
}
