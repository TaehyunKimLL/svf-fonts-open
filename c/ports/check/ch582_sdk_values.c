/* Compile-time check that the host stub c/ports/ch582/stub/CH58x_common.h and the real WCH SDK agree on every name and
 * value the host tests rely on. Compiled -fsyntax-only twice: against the stub (host-checks.sh) and against the SDK headers
 * (the cross compiler; see the ch582 port's README); a value that differs fails with a negative array size. */
#include "CH58x_common.h"

#define V(name, cond) typedef char name[(cond) ? 1 : -1]

V(v_disable, DISABLE == 0);
V(v_enable, ENABLE == 1);
V(v_reset, RESET == 0);
V(v_set, SET == 1);
V(v_pin4, GPIO_Pin_4 == 0x10);
V(v_pin20, GPIO_Pin_20 == 0x00100000);
V(v_pin21, GPIO_Pin_21 == 0x00200000);
V(v_in_floating, GPIO_ModeIN_Floating == 0);
V(v_in_pu, GPIO_ModeIN_PU == 1);
V(v_in_pd, GPIO_ModeIN_PD == 2);
V(v_out_5, GPIO_ModeOut_PP_5mA == 3);
V(v_out_20, GPIO_ModeOut_PP_20mA == 4);
V(v_remap, RB_PIN_I2C == 0x800);
V(v_pll60, CLK_SOURCE_PLL_60MHz == 0x48);
V(v_pll24, CLK_SOURCE_PLL_24MHz == 0x54);
V(v_mode, I2C_Mode_I2C == 0);
V(v_duty, I2C_DutyCycle_2 == 0x0000);
V(v_ack, I2C_Ack_Enable == 0x0400);
V(v_ackaddr, I2C_AckAddr_7bit == 0x4000);
V(v_dir, I2C_Direction_Transmitter == 0);
V(v_busy, I2C_FLAG_BUSY == 0x00020000);
V(v_af, I2C_FLAG_AF == 0x10000400);
V(v_txe, I2C_FLAG_TXE == 0x10000080);
V(v_ev_select, I2C_EVENT_MASTER_MODE_SELECT == 0x00030001);
V(v_ev_tx_selected, I2C_EVENT_MASTER_TRANSMITTER_MODE_SELECTED == 0x00070082);
V(v_ev_byte, I2C_EVENT_MASTER_BYTE_TRANSMITTED == 0x00070084);

#ifndef DelayMs
#error "DelayMs must be a macro (the SDK's is #define DelayMs(x) mDelaymS(x))"
#endif
