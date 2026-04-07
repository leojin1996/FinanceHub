import { render, screen } from "@testing-library/react";

import { MetricCard } from "./MetricCard";
import { RankingList } from "./RankingList";

describe("Shared finance components", () => {
  it("renders key market metrics", () => {
    render(<MetricCard label="上证指数" value="3,245.55" delta="+0.82%" tone="positive" />);

    expect(screen.getByText("上证指数")).toBeInTheDocument();
    expect(screen.getByText("3,245.55")).toBeInTheDocument();
    expect(screen.getByText("+0.82%")).toHaveAttribute("data-tone", "positive");
  });

  it("renders a ranking list with item labels", () => {
    render(
      <RankingList
        title="涨幅榜"
        items={[
          { name: "宁德时代", value: "+6.2%" },
          { name: "比亚迪", value: "+4.8%" },
        ]}
      />,
    );

    expect(screen.getByRole("heading", { name: "涨幅榜" })).toBeInTheDocument();
    expect(screen.getByText("宁德时代")).toBeInTheDocument();
  });
});
