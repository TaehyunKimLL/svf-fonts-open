/* Compile-check stub of the ESP-IDF calls main/main.c makes (c/cross/build-all.sh --ports); not the SDK. */
#ifndef STUB_ESP_ERR_H
#define STUB_ESP_ERR_H
typedef int esp_err_t;
#define ESP_OK 0
#define ESP_FAIL (-1)
#define ESP_ERR_INVALID_ARG 0x102
#define ESP_ERROR_CHECK(x) \
	do { \
		if ((x) != ESP_OK) \
			for (;;) \
				; \
	} while (0)
#endif
