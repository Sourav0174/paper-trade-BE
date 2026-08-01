"""
FIFO Position Reconstruction Engine.

Converts raw, un-paired execution trades (BUY/SELL) into matched closed position
chunks and consolidated closed position campaigns using First-In, First-Out (FIFO)
inventory accounting.
"""

from collections import defaultdict, deque
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence
import hashlib
import uuid

from app.mentor.schema import (
    ClosedPosition,
    ClosedTradeChunk,
    FifoReconstructionResult,
    OpenPositionState,
    TradeInput,
    TradeLot,
)


class FIFOReconstructor:
    """
    Pure deterministic FIFO matching engine.

    Parses chronological execution logs for a user and calculates:
    1. Sub-lot matched trade chunks (ClosedTradeChunk)
    2. Consolidated round-trip position campaigns (ClosedPosition)
    3. Active open holdings and remaining buy lots (OpenPositionState)
    """

    @classmethod
    def process_trades(cls, raw_trades: Sequence[Any]) -> FifoReconstructionResult:
        """
        Main entrypoint for FIFO reconstruction.

        Args:
            raw_trades: Sequence of TradeInput, dicts, or ORM models.

        Returns:
            FifoReconstructionResult containing closed positions, chunks, open states, and unmatched sells.
        """
        normalized_trades = cls._normalize_trades(raw_trades)

        # Sort strictly by timestamp ASC, breaking ties by trade ID
        sorted_trades = sorted(
            normalized_trades,
            key=lambda t: (t.created_at, str(t.id))
        )

        # Group trades by symbol
        symbol_trades: Dict[str, List[TradeInput]] = defaultdict(list)
        for trade in sorted_trades:
            symbol_trades[trade.symbol.upper().strip()].append(trade)

        all_closed_chunks: List[ClosedTradeChunk] = []
        all_closed_positions: List[ClosedPosition] = []
        open_positions_map: Dict[str, OpenPositionState] = {}
        unmatched_sells: List[dict] = []

        for symbol, trades in symbol_trades.items():
            chunks, open_state, unmatched = cls._process_symbol_trades(symbol, trades)
            all_closed_chunks.extend(chunks)
            if unmatched:
                unmatched_sells.extend(unmatched)

            if open_state and open_state.total_quantity > 0:
                open_positions_map[symbol] = open_state

            positions = cls._group_chunks_into_positions(symbol, chunks)
            all_closed_positions.extend(positions)

        # Sort closed positions by close_timestamp ASC
        all_closed_positions.sort(key=lambda p: p.close_timestamp)
        all_closed_chunks.sort(key=lambda c: c.sell_timestamp)

        return FifoReconstructionResult(
            closed_positions=all_closed_positions,
            closed_chunks=all_closed_chunks,
            open_positions=open_positions_map,
            unmatched_sells=unmatched_sells,
        )

    @classmethod
    def _normalize_trades(cls, raw_trades: Sequence[Any]) -> List[TradeInput]:
        """Converts heterogeneous input objects (dicts, ORM models, TradeInput) into TradeInput list."""
        normalized: List[TradeInput] = []

        for item in raw_trades:
            if isinstance(item, TradeInput):
                normalized.append(item)
            elif isinstance(item, dict):
                normalized.append(TradeInput(**item))
            else:
                # Support SQLAlchemy or generic duck-typed model
                trade_type_val = getattr(item, "trade_type", "BUY")
                if hasattr(trade_type_val, "value"):
                    trade_type_val = trade_type_val.value

                normalized.append(
                    TradeInput(
                        id=getattr(item, "id"),
                        symbol=str(getattr(item, "symbol")),
                        quantity=int(getattr(item, "quantity")),
                        price=float(getattr(item, "price")),
                        trade_type=str(trade_type_val).upper(),
                        created_at=getattr(item, "created_at"),
                    )
                )

        return normalized

    @classmethod
    def _process_symbol_trades(
        cls,
        symbol: str,
        trades: List[TradeInput]
    ) -> tuple[List[ClosedTradeChunk], Optional[OpenPositionState], List[dict]]:
        """Applies FIFO queue logic for a single stock symbol."""
        buy_queue: deque[TradeLot] = deque()
        closed_chunks: List[ClosedTradeChunk] = []
        unmatched_sells: List[dict] = []

        for trade in trades:
            if trade.trade_type == "BUY":
                buy_queue.append(
                    TradeLot(
                        trade_id=trade.id,
                        symbol=symbol,
                        price=trade.price,
                        quantity=trade.quantity,
                        remaining_quantity=trade.quantity,
                        timestamp=trade.created_at,
                    )
                )
            elif trade.trade_type == "SELL":
                sell_qty_remaining = trade.quantity

                while sell_qty_remaining > 0 and buy_queue:
                    earliest_lot = buy_queue[0]
                    matched_qty = min(sell_qty_remaining, earliest_lot.remaining_quantity)

                    pnl = round((trade.price - earliest_lot.price) * matched_qty, 4)
                    cost_basis = earliest_lot.price * matched_qty
                    pnl_pct = round((pnl / cost_basis) * 100, 4) if cost_basis > 0 else 0.0

                    duration_seconds = (trade.created_at - earliest_lot.timestamp).total_seconds()
                    duration_minutes = round(max(0.0, duration_seconds / 60.0), 2)

                    chunk = ClosedTradeChunk(
                        buy_trade_id=earliest_lot.trade_id,
                        sell_trade_id=trade.id,
                        symbol=symbol,
                        buy_price=earliest_lot.price,
                        sell_price=trade.price,
                        quantity=matched_qty,
                        buy_timestamp=earliest_lot.timestamp,
                        sell_timestamp=trade.created_at,
                        pnl=pnl,
                        pnl_percent=pnl_pct,
                        duration_minutes=duration_minutes,
                    )
                    closed_chunks.append(chunk)

                    earliest_lot.remaining_quantity -= matched_qty
                    sell_qty_remaining -= matched_qty

                    if earliest_lot.remaining_quantity == 0:
                        buy_queue.popleft()

                if sell_qty_remaining > 0:
                    unmatched_sells.append({
                        "trade_id": trade.id,
                        "symbol": symbol,
                        "unmatched_quantity": sell_qty_remaining,
                        "price": trade.price,
                        "timestamp": trade.created_at.isoformat(),
                    })

        open_state = cls._build_open_position_state(symbol, list(buy_queue))
        return closed_chunks, open_state, unmatched_sells

    @staticmethod
    def _build_open_position_state(symbol: str, open_lots: List[TradeLot]) -> Optional[OpenPositionState]:
        """Constructs OpenPositionState from remaining buy lots."""
        active_lots = [lot for lot in open_lots if lot.remaining_quantity > 0]

        if not active_lots:
            return None

        total_qty = sum(lot.remaining_quantity for lot in active_lots)
        total_cost = sum(lot.price * lot.remaining_quantity for lot in active_lots)
        weighted_avg_buy = round(total_cost / total_qty, 4) if total_qty > 0 else 0.0

        return OpenPositionState(
            symbol=symbol,
            total_quantity=total_qty,
            weighted_avg_buy_price=weighted_avg_buy,
            total_invested_amount=round(total_cost, 2),
            earliest_buy_timestamp=min(lot.timestamp for lot in active_lots),
            lots=active_lots,
        )

    @classmethod
    def _group_chunks_into_positions(cls, symbol: str, chunks: List[ClosedTradeChunk]) -> List[ClosedPosition]:
        """
        Aggregates matched chunks into consolidated closed position campaigns.

        Chunks that occur within a continuous open-to-close position cycle are grouped
        into a single ClosedPosition object for intuitive behavioral analysis.
        """
        if not chunks:
            return []

        # Sort chunks by sell timestamp ASC
        sorted_chunks = sorted(chunks, key=lambda c: (c.sell_timestamp, c.buy_timestamp))

        position_campaigns: List[List[ClosedTradeChunk]] = []
        current_campaign: List[ClosedTradeChunk] = []

        for chunk in sorted_chunks:
            if not current_campaign:
                current_campaign.append(chunk)
            else:
                last_chunk = current_campaign[-1]
                # If current chunk's buy timestamp is before or equal to previous sell timestamp,
                # it is part of the same continuous open trade cycle.
                if chunk.buy_timestamp <= last_chunk.sell_timestamp:
                    current_campaign.append(chunk)
                else:
                    position_campaigns.append(current_campaign)
                    current_campaign = [chunk]

        if current_campaign:
            position_campaigns.append(current_campaign)

        closed_positions: List[ClosedPosition] = []

        for campaign in position_campaigns:
            pos = cls._aggregate_campaign_chunks(symbol, campaign)
            closed_positions.append(pos)

        return closed_positions

    @staticmethod
    def _aggregate_campaign_chunks(symbol: str, chunks: List[ClosedTradeChunk]) -> ClosedPosition:
        """Computes weighted summary metrics for a list of campaign chunks."""
        total_qty = sum(c.quantity for c in chunks)
        total_buy_cost = sum(c.buy_price * c.quantity for c in chunks)
        total_sell_value = sum(c.sell_price * c.quantity for c in chunks)

        weighted_buy = round(total_buy_cost / total_qty, 4) if total_qty > 0 else 0.0
        weighted_sell = round(total_sell_value / total_qty, 4) if total_qty > 0 else 0.0

        realized_pnl = round(total_sell_value - total_buy_cost, 2)
        realized_pnl_pct = round((realized_pnl / total_buy_cost) * 100, 4) if total_buy_cost > 0 else 0.0

        open_ts = min(c.buy_timestamp for c in chunks)
        close_ts = max(c.sell_timestamp for c in chunks)
        duration_mins = round(max(0.0, (close_ts - open_ts).total_seconds() / 60.0), 2)

        pos_hash = hashlib.md5(
            f"{symbol}_{open_ts.isoformat()}_{close_ts.isoformat()}_{total_qty}_{realized_pnl}".encode("utf-8")
        ).hexdigest()[:8]
        position_id = f"pos_{symbol.lower()}_{open_ts.strftime('%Y%m%d%H%M%S')}_{pos_hash}"

        return ClosedPosition(
            position_id=position_id,
            symbol=symbol,
            total_quantity=total_qty,
            weighted_avg_buy_price=weighted_buy,
            weighted_avg_sell_price=weighted_sell,
            realized_pnl=realized_pnl,
            realized_pnl_percent=realized_pnl_pct,
            open_timestamp=open_ts,
            close_timestamp=close_ts,
            holding_duration_minutes=duration_mins,
            is_win=realized_pnl > 0,
            is_loss=realized_pnl < 0,
            is_breakeven=realized_pnl == 0,
            chunks=chunks,
        )
