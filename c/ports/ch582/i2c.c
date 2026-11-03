/* i2c.c - one polled I2C master write on the SDK's API, in the order of the SDK's I2C example, with every wait
 * bounded (CH582_I2C_SPIN polls) and cut short by a NACK (I2C_FLAG_AF). */
#include "CH58x_common.h"
#include "i2c.h"

/* Poll until the flag is clear (@p want_set 0: BUSY) or set (@p want_set 1: TXE), or the event is complete
 * (@p flag 0: @p ev). AF is read before the awaited condition, every iteration. 0 when it came; -1 on timeout or
 * AF, with *af set when AF was the reason. */
static int wait_for(uint32_t ev, uint32_t flag, int want_set, int *af)
{
	int i;

	for (i = 0; i < CH582_I2C_SPIN; ++i) {
		/* AF first: TXE or an event bit can be set next to a NACK, and the next byte must not go out then */
		if (I2C_GetFlagStatus(I2C_FLAG_AF) == SET) {
			*af = 1;
			return -1;
		}
		if (flag ? ((I2C_GetFlagStatus(flag) == SET) == want_set) : I2C_CheckEvent(ev))
			return 0;
	}
	return -1;
}

int ch582_i2c_write(uint8_t addr, const uint8_t *buf, size_t n)
{
	int af = 0;
	size_t i;

	if (!buf || n == 0 || addr > 0x7F)
		return -1;
	if (wait_for(0, I2C_FLAG_BUSY, 0, &af))
		goto fail;
	I2C_GenerateSTART(ENABLE);
	if (wait_for(I2C_EVENT_MASTER_MODE_SELECT, 0, 0, &af))
		goto fail;
	I2C_Send7bitAddress((uint8_t)(addr << 1), I2C_Direction_Transmitter);
	if (wait_for(I2C_EVENT_MASTER_TRANSMITTER_MODE_SELECTED, 0, 0, &af))
		goto fail;
	for (i = 0; i < n; ++i) {
		if (wait_for(0, I2C_FLAG_TXE, 1, &af))
			goto fail;
		I2C_SendData(buf[i]);
	}
	if (wait_for(I2C_EVENT_MASTER_BYTE_TRANSMITTED, 0, 0, &af))
		goto fail;
	I2C_GenerateSTOP(ENABLE);
	return 0;
fail:
	if (af)
		I2C_ClearFlag(I2C_FLAG_AF);
	I2C_GenerateSTOP(ENABLE);
	return -1;
}
