from __future__ import annotations

from io import BytesIO
from datetime import date

import matplotlib
# matplotlib.use("Agg")  # важно для серверов без GUI
import matplotlib.pyplot as plt  # noqa

from aiogram.types import BufferedInputFile


def kcal_line_chart(dates: list[date], values: list[float], title: str) -> BufferedInputFile:
    fig = plt.figure()
    ax = fig.add_subplot(1, 1, 1)

    # matplotlib сам выберет цвета (мы не задаём)
    ax.plot(dates, values, marker="o")
    ax.set_title(title)
    ax.set_ylabel("Ккал")
    ax.set_xlabel("День")

    fig.autofmt_xdate(rotation=45)
    fig.tight_layout()

    buf = BytesIO()
    fig.savefig(buf, format="png", dpi=150)
    plt.close(fig)
    buf.seek(0)

    return BufferedInputFile(buf.read(), filename="chart.png")
