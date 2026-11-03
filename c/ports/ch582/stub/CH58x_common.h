/* openwch/ch583 bd508ad7ceed48377619837051412a651952857f, Apache-2.0; host stand-in with the SDK's names and values,
 * not WCH code.
 * CH58x_common.h - host stand-in for the WCH CH583 EVT SDK header of the same name (host checks only; not the SDK).
 * The names and values are the SDK's (StdPeriphDriver/inc, RVMSIS/core_riscv.h at the pinned commit); the test
 * c/ports/check/ch582_sdk_values.c holds each value to the real headers. The calls record under SVF_STUB_RECORD
 * (svf_stub_record.h) and are no-ops without it. The I2C data-path functions have no body here: a test defines them
 * (c/ports/check/test_ch582_i2c.c). */
#ifndef STUB_CH58X_COMMON_H
#define STUB_CH58X_COMMON_H
#include <stdint.h>
#include "svf_stub_record.h"

typedef enum { DISABLE = 0, ENABLE = !DISABLE } FunctionalState;
typedef enum { RESET = 0, SET = !RESET } FlagStatus;

#define GPIO_Pin_4  (0x00000010)
#define GPIO_Pin_20 (0x00100000)
#define GPIO_Pin_21 (0x00200000)
typedef enum {
	GPIO_ModeIN_Floating,
	GPIO_ModeIN_PU,
	GPIO_ModeIN_PD,
	GPIO_ModeOut_PP_5mA,
	GPIO_ModeOut_PP_20mA,
} GPIOModeTypeDef;

#define RB_PIN_I2C 0x800
typedef enum { CLK_SOURCE_PLL_60MHz = 0x48, CLK_SOURCE_PLL_24MHz = 0x54 } SYS_CLKTypeDef;

typedef enum { I2C_Mode_I2C = 0x0000 } I2C_ModeTypeDef;
typedef enum { I2C_DutyCycle_16_9 = 0x4000, I2C_DutyCycle_2 = 0x0000 } I2C_DutyTypeDef;
typedef enum { I2C_Ack_Enable = 0x0400, I2C_Ack_Disable = 0x0000 } I2C_AckTypeDef;
typedef enum { I2C_AckAddr_7bit = 0x4000, I2C_AckAddr_10bit = 0xC000 } I2C_AckAddrTypeDef;
#define I2C_Direction_Transmitter ((uint8_t)0x00)
#define I2C_FLAG_BUSY ((uint32_t)0x00020000)
#define I2C_FLAG_AF ((uint32_t)0x10000400)
#define I2C_FLAG_TXE ((uint32_t)0x10000080)
#define I2C_EVENT_MASTER_MODE_SELECT ((uint32_t)0x00030001)
#define I2C_EVENT_MASTER_TRANSMITTER_MODE_SELECTED ((uint32_t)0x00070082)
#define I2C_EVENT_MASTER_BYTE_TRANSMITTED ((uint32_t)0x00070084)

static inline void SetSysClock(SYS_CLKTypeDef sc)
{
#ifdef SVF_STUB_RECORD
	svf_rec_cfg(SVF_CFG_SYSCLK, (int)sc, 0, 0, 0);
#else
	(void)sc;
#endif
}

static inline void GPIOPinRemap(FunctionalState s, uint16_t perph)
{
#ifdef SVF_STUB_RECORD
	svf_rec_cfg(SVF_CFG_PIN_REMAP, (int)s, (int)perph, 0, 0);
#else
	(void)s; (void)perph;
#endif
}

static inline void GPIOB_ModeCfg(uint32_t pin, GPIOModeTypeDef mode)
{
#ifdef SVF_STUB_RECORD
	svf_rec_cfg(SVF_CFG_GPIOB_MODE, (int)pin, (int)mode, 0, 0);
#else
	(void)pin; (void)mode;
#endif
}

static inline void I2C_Init(I2C_ModeTypeDef mode, uint32_t speed, I2C_DutyTypeDef duty, I2C_AckTypeDef ack,
			    I2C_AckAddrTypeDef ackaddr, uint16_t own)
{
#ifdef SVF_STUB_RECORD
	svf_rec_cfg(SVF_CFG_CH58X_I2C, (int)speed, (int)duty, (int)ack, (int)ackaddr);
#else
	(void)speed; (void)duty; (void)ack; (void)ackaddr;
#endif
	(void)mode; (void)own;
}

static inline void svf_stub_delay_ms(uint32_t ms)
{
#ifdef SVF_STUB_RECORD
	svf_rec_sleep(ms);
#else
	(void)ms;
#endif
}
#define DelayMs(x) svf_stub_delay_ms(x) /* the SDK's is a macro too (mDelaymS) */

/* PB output word of this translation unit (starts 0); the level reported is that of the pins after the call */
static uint32_t svf_stub_pb_out;
static inline void svf_stub_pb(uint32_t pin)
{
#ifdef SVF_STUB_RECORD
	svf_rec_gpio((int)pin, (svf_stub_pb_out & pin) != 0);
#else
	(void)pin;
#endif
}
static inline void GPIOB_SetBits(uint32_t pin) { svf_stub_pb_out |= pin; svf_stub_pb(pin); }
static inline void GPIOB_ResetBits(uint32_t pin) { svf_stub_pb_out &= ~pin; svf_stub_pb(pin); }
static inline void GPIOB_InverseBits(uint32_t pin) { svf_stub_pb_out ^= pin; svf_stub_pb(pin); }

void I2C_GenerateSTART(FunctionalState NewState);
void I2C_GenerateSTOP(FunctionalState NewState);
void I2C_Send7bitAddress(uint8_t Address, uint8_t I2C_Direction);
void I2C_SendData(uint8_t Data);
uint8_t I2C_CheckEvent(uint32_t I2C_EVENT);
FlagStatus I2C_GetFlagStatus(uint32_t I2C_FLAG);
void I2C_ClearFlag(uint32_t I2C_FLAG);

#endif
