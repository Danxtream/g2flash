#include <stdint.h>

static const uint8_t table[4] = { 10, 20, 30, 40 };

extern "C" uint8_t test_table(unsigned i)
{
    return table[i & 3];
}
