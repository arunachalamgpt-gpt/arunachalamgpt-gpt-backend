"""Planning recommendation logic (Step 3 of the user journey).

Rule-based, no AI — keeps the decision auditable and offline-testable.

Decision matrix:

| has_elderly | has_children | recommended_arrival | recommended_line |
|-------------|--------------|---------------------|------------------|
| true        | any          | 4:30 AM (before sunrise rush) | Rs.200 ticket    |
| false       | true         | 4:30 AM             | Rs.200 ticket    |
| false       | false        | 8:00 AM – 10:00 AM   | Rs.50 ticket     |

The packing checklist is composed from the same flags.
"""

from datetime import date as date_t

from app.schemas.devotee import PlanningRecommendationResponse


def recommend(
    *,
    visit_date: date_t,
    has_elderly: bool,
    has_children: bool,
    is_pournami: bool = False,
    is_festival: bool = False,
) -> PlanningRecommendationResponse:
    needs_early = has_elderly or has_children or is_festival or is_pournami
    if needs_early:
        arrival = "4:30 AM (before the sunrise rush)"
        line = "Rs.200 ticket — shortest queue (15-25 minutes)"
        rationale = (
            "With elderly or children in the group, plan to arrive early and use "
            "the Rs.200 line so the wait stays under 30 minutes."
        )
    else:
        arrival = "8:00 AM – 10:00 AM"
        line = "Rs.50 ticket — short queue (40-60 minutes) at a moderate price"
        rationale = (
            "No elderly or children — a mid-morning arrival with the Rs.50 ticket "
            "balances cost and queue length."
        )
    if is_festival:
        rationale = (
            "Karthigai Deepam — expect very heavy crowds. " + rationale +
            " Carry water and avoid the hottest part of the day."
        )
    elif is_pournami:
        rationale = (
            "Pournami (full-moon) Girivalam day — crowds are heavier than usual. " +
            rationale
        )

    checklist = ["Water bottle (1 litre per person)", "Comfortable walking footwear"]
    if has_elderly:
        checklist.extend(
            [
                "Folding stool / camp chair for the elderly",
                "Any prescription medication for the day",
                "Note nearest medical point location",
            ]
        )
    if has_children:
        checklist.extend(
            [
                "Snacks for the children",
                "Hand sanitiser and wet wipes",
            ]
        )
    checklist.append("Small change for ticket counter (Rs.50 / Rs.200)")

    return PlanningRecommendationResponse(
        visit_date=visit_date,
        has_elderly=has_elderly,
        has_children=has_children,
        recommended_arrival=arrival,
        recommended_line=line,
        rationale=rationale,
        packing_checklist=checklist,
    )
