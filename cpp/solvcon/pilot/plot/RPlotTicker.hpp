#pragma once

/*
 * Copyright (c) 2026, solvcon team <contact@solvcon.net>
 * BSD 3-Clause License, see COPYING
 */

/**
 * @file
 * Round tick positions and labels for the axes of a native xy plot. Qt-free,
 * so it compiles into the no-GUI test target.
 *
 * @ingroup group_domain
 */

#include <cstddef>
#include <string>

#include <solvcon/buffer/small_vector.hpp>

#include <solvcon/pilot/plot/plot_style.hpp>

namespace solvcon
{

/**
 * Locate 1-2-5 ticks over a linear range, or whole decades over a log range,
 * and format their short labels.
 */
class RPlotTicker
{
public:

    using ticks_type = small_vector<double, 16>;

    RPlotTicker() = default;
    explicit RPlotTicker(std::size_t target_count);
    RPlotTicker(RPlotTicker const &) = default;
    RPlotTicker(RPlotTicker &&) = default;
    RPlotTicker & operator=(RPlotTicker const &) = default;
    RPlotTicker & operator=(RPlotTicker &&) = default;
    ~RPlotTicker() = default;

    std::size_t target_count() const { return m_target_count; }
    void set_target_count(std::size_t count);

    ticks_type locate(double lo, double hi) const;
    ticks_type locate_decades(double lo, double hi) const;

    std::string label(double value) const;
    std::string decade_label(double value) const;

private:

    std::size_t m_target_count = PLOT_DEFAULT_TICK_COUNT;
}; /* end class RPlotTicker */

} /* end namespace solvcon */

// vim: set ff=unix fenc=utf8 et sw=4 ts=4 sts=4:
