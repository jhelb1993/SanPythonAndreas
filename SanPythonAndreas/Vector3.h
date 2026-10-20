#pragma once
#include <cmath>
#include <stdexcept>

// A detached value, never a view of game memory. No Windows or Python dependency.
class Vector3
{
public:
    const double x, y, z;

    Vector3(double xValue = 0, double yValue = 0, double zValue = 0)
        : x(xValue), y(yValue), z(zValue)
    {
        if (!std::isfinite(x) || !std::isfinite(y) || !std::isfinite(z))
            throw std::invalid_argument("Vector3 components must be finite");
    }

    Vector3 operator+(const Vector3& other) const { return {x + other.x, y + other.y, z + other.z}; }
    Vector3 operator-(const Vector3& other) const { return {x - other.x, y - other.y, z - other.z}; }
    Vector3 operator-() const { return {-x, -y, -z}; }
    Vector3 operator*(double scalar) const { return {x * scalar, y * scalar, z * scalar}; }
    Vector3 operator/(double scalar) const
    {
        if (!std::isfinite(scalar))
            throw std::invalid_argument("Vector3 divisor must be finite");
        if (scalar == 0)
            throw std::domain_error("cannot divide Vector3 by zero");
        return {x / scalar, y / scalar, z / scalar};
    }
    bool operator==(const Vector3& other) const { return x == other.x && y == other.y && z == other.z; }
    bool operator!=(const Vector3& other) const { return !(*this == other); }
    double Length() const { return std::hypot(x, y, z); }
    double DistanceTo(const Vector3& other) const { return (*this - other).Length(); }
};
inline Vector3 operator*(double scalar, const Vector3& vector) { return vector * scalar; }
