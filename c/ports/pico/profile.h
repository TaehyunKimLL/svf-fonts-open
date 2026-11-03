/* profile.h - what every profile (profile_colour.c, profile_grey.c, profile_mono.c) offers main.c and the host test. */
#ifndef PORT_PROFILE_H
#define PORT_PROFILE_H

/* Draws the profile's screen and shows it through display_show. On any svf_* failure it calls svf_port_idle() and
 * shows nothing (no BKPT, no stdio). Reads its marker svf_port_profile_<profile> once through a volatile pointer. */
void profile_run(void);
/* main.c: never returns; an own, non-inlined symbol the screen runner looks up (sleep_ms(1000) for ever). */
void svf_port_idle(void);
extern const char *const svf_port_text[]; /* the profile's lines, in draw order */
extern const int svf_port_text_n;

#endif
