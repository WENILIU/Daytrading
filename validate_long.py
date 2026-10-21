import pickle, pandas as pd, numpy as np
import warnings
warnings.filterwarnings('ignore')

# Load 16-year daily signals
signals = pickle.load(open(r'C:\Users\weni.liu\Documents\Codex\2026-10-14\new-chat-3\outputs\gap_fade_signals_2010.pkl', 'rb'))
print(f"Signals: {type(signals)}")
if isinstance(signals, pd.DataFrame):
    print(f"Shape: {signals.shape}")
    print(f"Columns: {list(signals.columns)}")
    print(signals.head(2))
    print(f"\nDate range: {signals['date'].min()} to {signals['date'].max()}")
    print(f"Directions: {signals['direction'].value_counts().to_dict()}")
