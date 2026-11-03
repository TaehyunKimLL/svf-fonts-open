/* sdl_compat.h - the whole difference between SDL2 and SDL3 the SDL port touches. The build passes -DSVFSDL=2 or 3 only
 * to pick the include; everything else keys on SDL_VERSION_ATLEAST(3, 0, 0), as ScummVM's backends do. */
#ifndef SVFSDL_COMPAT_H
#define SVFSDL_COMPAT_H

#define SDL_MAIN_HANDLED
#if SVFSDL == 3
#include <SDL3/SDL.h>
#include <SDL3/SDL_main.h> /* SDL_SetMainReady */
#else
#include <SDL.h>
#endif

#if SDL_VERSION_ATLEAST(3, 0, 0)
typedef SDL_PixelFormat svfsdl_format;
#define SVFSDL_OK(call) (call) /* SDL3: bool, true on success */
#define SVFSDL_EVENT_QUIT SDL_EVENT_QUIT
#define SVFSDL_EVENT_KEY_DOWN SDL_EVENT_KEY_DOWN
static inline int svfsdl_major(void) { return 3; }
static inline SDL_Window *svfsdl_create_window(const char *t, int w, int h) { return SDL_CreateWindow(t, w, h, 0); }
static inline SDL_Surface *svfsdl_create_surface(int w, int h, svfsdl_format f) { return SDL_CreateSurface(w, h, f); }
static inline void svfsdl_destroy_surface(SDL_Surface *s) { SDL_DestroySurface(s); }
static inline svfsdl_format svfsdl_surface_format(const SDL_Surface *s) { return s->format; }
/* SDL3 gives an indexed surface no palette until asked */
static inline SDL_Palette *svfsdl_surface_palette(SDL_Surface *s)
{
	SDL_Palette *p = SDL_GetSurfacePalette(s);
	return p ? p : SDL_CreateSurfacePalette(s);
}
static inline SDL_Renderer *svfsdl_create_renderer(SDL_Window *w) { return SDL_CreateRenderer(w, NULL); }
static inline SDL_Texture *svfsdl_create_texture(SDL_Renderer *r, svfsdl_format f, int w, int h)
{
	return SDL_CreateTexture(r, f, SDL_TEXTUREACCESS_STREAMING, w, h);
}
static inline int svfsdl_render_copy(SDL_Renderer *r, SDL_Texture *t) { return SDL_RenderTexture(r, t, NULL, NULL); }
/* SDL_GetVersion returns the packed number in SDL3, fills a struct in SDL2 */
static inline void svfsdl_version(int *x, int *y, int *z)
{
	int v = SDL_GetVersion();
	*x = SDL_VERSIONNUM_MAJOR(v), *y = SDL_VERSIONNUM_MINOR(v), *z = SDL_VERSIONNUM_MICRO(v);
}
#else
#if !SDL_VERSION_ATLEAST(2, 30, 0)
#error "svfsdl needs SDL 2.30.0 or newer (SDL_PIXELFORMAT_INDEX2MSB/LSB)"
#endif
typedef Uint32 svfsdl_format;
#define SVFSDL_OK(call) ((call) == 0) /* SDL2: int, 0 on success */
#define SVFSDL_EVENT_QUIT SDL_QUIT
#define SVFSDL_EVENT_KEY_DOWN SDL_KEYDOWN
#ifndef SDL_PIXELFORMAT_XRGB8888
#define SDL_PIXELFORMAT_XRGB8888 SDL_PIXELFORMAT_RGB888
#endif
static inline int svfsdl_major(void) { return 2; }
static inline SDL_Window *svfsdl_create_window(const char *t, int w, int h)
{
	return SDL_CreateWindow(t, SDL_WINDOWPOS_UNDEFINED, SDL_WINDOWPOS_UNDEFINED, w, h, 0);
}
static inline SDL_Surface *svfsdl_create_surface(int w, int h, svfsdl_format f)
{
	return SDL_CreateRGBSurfaceWithFormat(0, w, h, 0, f);
}
static inline void svfsdl_destroy_surface(SDL_Surface *s) { SDL_FreeSurface(s); }
static inline svfsdl_format svfsdl_surface_format(const SDL_Surface *s) { return s->format->format; }
static inline SDL_Palette *svfsdl_surface_palette(SDL_Surface *s) { return s->format->palette; }
static inline SDL_Renderer *svfsdl_create_renderer(SDL_Window *w) { return SDL_CreateRenderer(w, -1, 0); }
static inline SDL_Texture *svfsdl_create_texture(SDL_Renderer *r, svfsdl_format f, int w, int h)
{
	return SDL_CreateTexture(r, f, SDL_TEXTUREACCESS_STREAMING, w, h);
}
static inline int svfsdl_render_copy(SDL_Renderer *r, SDL_Texture *t) { return SDL_RenderCopy(r, t, NULL, NULL) == 0; }
static inline void svfsdl_version(int *x, int *y, int *z)
{
	SDL_version v;
	SDL_GetVersion(&v);
	*x = v.major, *y = v.minor, *z = v.patch;
}
#endif

#endif
