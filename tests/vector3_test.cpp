#include "../SanPythonAndreas/Vector3.h"
#include <limits>
#include <stdexcept>

void Check(bool condition)
{
    if (!condition) throw std::runtime_error("Vector3 test failed");
}
int main()
{
    const Vector3 value(3, 4, 12);
    Check(std::abs(value.Length() - 13) < 1e-12);
    Check(value + Vector3(1, -2, 0) == Vector3(4, 2, 12));
    Check(value - Vector3(1, 2, 3) == Vector3(2, 2, 9));
    Check(-value == Vector3(-3, -4, -12));
    Check(2 * value == value * 2);
    Check(value / 2 == Vector3(1.5, 2, 6));
    Check(std::abs(value.DistanceTo(Vector3()) - 13) < 1e-12);
    Check(value == Vector3(3, 4, 12));
    Check(value != Vector3());
    Check(std::isfinite(Vector3(1e300, 1e300, 0).Length()));
    bool caught = false;
    try { (void)(value / 0); } catch (const std::domain_error&) { caught = true; }
    Check(caught);
    for (double bad : {std::numeric_limits<double>::infinity(), std::numeric_limits<double>::quiet_NaN()})
    {
        caught = false;
        try { (void)Vector3(bad, 0, 0); } catch (const std::invalid_argument&) { caught = true; }
        Check(caught);
        caught = false;
        try { (void)(value * bad); } catch (const std::invalid_argument&) { caught = true; }
        Check(caught);
    }
}
