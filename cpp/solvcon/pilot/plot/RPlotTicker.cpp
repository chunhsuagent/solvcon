/*
 * Copyright (c) 2026, solvcon team <contact@solvcon.net>
 * BSD 3-Clause License, see COPYING
 */

#include <solvcon/pilot/plot/RPlotTicker.hpp>

#include <algorithm>
#include <cmath>
#include <format>
#include <limits>
#include <stdexcept>

namespace solvcon
{

namespace
{

constexpr double TICK_BOUND_SLACK = 1e-9;
constexpr double PLAIN_LABEL_MINIMUM = 1e-3;
constexpr double PLAIN_LABEL_MAXIMUM = 1e5;

} /* end namespace */

RPlotTicker::RPlotTicker(std::size_t target_count)
{
    set_target_count(target_count);
}

void RPlotTicker::set_target_count(std::size_t count)
{
    if (count < 1)
    {
        throw std::invalid_argument(
            std::format("RPlotTicker::set_target_count: target count must be at least 1, but it is {}", count));
    }
    m_target_count = count;
}

RPlotTicker::ticks_type RPlotTicker::locate(double lo, double hi) const
{
    double const span = hi - lo;
    if (!std::isfinite(span) || !(span > 0.0))
    {
        return {};
    }

    double const raw_step = span / static_cast<double>(m_target_count);
    if (!std::isfinite(raw_step) || !(raw_step > 0.0))
    {
        return {};
    }

    double const magnitude = std::pow(10.0, std::floor(std::log10(raw_step)));
    if (!std::isfinite(magnitude) || !(magnitude > 0.0))
    {
        return {};
    }

    double step = 0.0;
    for (double multiplier : {1.0, 2.0, 5.0, 10.0})
    {
        double const candidate = multiplier * magnitude;
        if (!std::isfinite(candidate))
        {
            break;
        }
        step = candidate;
        if (raw_step <= step)
        {
            break;
        }
    }
    if (!std::isfinite(step) || !(step > 0.0) || raw_step > step)
    {
        return {};
    }

    double const first = std::ceil(lo / step);
    double const last = std::floor((hi + TICK_BOUND_SLACK * step) / step);
    double const count = last - first + 1.0;
    if (!std::isfinite(first) || !std::isfinite(last) || !std::isfinite(count))
    {
        return {};
    }

    double const maximum_count = static_cast<double>(m_target_count) + 2.0;
    double const maximum_size =
        static_cast<double>(std::numeric_limits<std::size_t>::max());
    if (!(count > 0.0) || count > maximum_count || !(count < maximum_size))
    {
        return {};
    }

    ticks_type ticks;
    std::size_t const tick_count = static_cast<std::size_t>(count);
    for (std::size_t it = 0; it < tick_count; ++it)
    {
        // Rebuild from the index so a small step advances at a large offset.
        double const index = first + static_cast<double>(it);
        double const value = (index == 0.0) ? 0.0 : std::clamp(index * step, lo, hi);
        ticks.push_back(value);
    }
    return ticks;
}

RPlotTicker::ticks_type RPlotTicker::locate_decades(double lo, double hi) const
{
    if (!std::isfinite(lo) || !std::isfinite(hi))
    {
        return {};
    }

    double const first = std::ceil(lo);
    double const last = std::floor(hi);
    if (last < first)
    {
        return {lo, hi};
    }

    double const count = last - first + 1.0;
    double const maximum_size =
        static_cast<double>(std::numeric_limits<std::size_t>::max());
    if (!std::isfinite(count) || !(count > 0.0) || !(count < maximum_size))
    {
        return {};
    }

    ticks_type ticks;
    std::size_t const tick_count = static_cast<std::size_t>(count);
    for (std::size_t it = 0; it < tick_count; ++it)
    {
        ticks.push_back(first + static_cast<double>(it));
    }
    return ticks;
}

std::string RPlotTicker::label(double value) const
{
    if (value == 0.0)
    {
        return "0";
    }

    double const magnitude = std::abs(value);
    if (PLAIN_LABEL_MINIMUM <= magnitude && magnitude < PLAIN_LABEL_MAXIMUM)
    {
        return std::format("{:.4g}", value);
    }
    return std::format("{:.0e}", value);
}

std::string RPlotTicker::decade_label(double value) const
{
    if (std::isfinite(value) && std::floor(value) == value)
    {
        return std::format("1e{:.0f}", value);
    }
    return label(std::pow(10.0, value));
}

} /* end namespace solvcon */

// vim: set ff=unix fenc=utf8 et sw=4 ts=4 sts=4:
