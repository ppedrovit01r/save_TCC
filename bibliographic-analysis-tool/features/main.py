import streamlit as st
import pandas as pd
from features.network_topology import show as show_network_topology

def show():
    show_network_topology()