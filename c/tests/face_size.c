/* face_size - prints sizeof(svf_face) for tools/test_c_renderer.py (the face state budget, spec "Budgets"). */
#include "svf.h"

#include <stdio.h>

int main(void)
{
	printf("%u\n", (unsigned)sizeof(svf_face));
	return 0;
}
