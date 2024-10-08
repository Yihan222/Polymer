from __future__ import annotations

import logging
from multiprocessing.spawn import _main
import pprint
import re
from typing import Dict, Tuple

from rdkit import Chem
import datamol as dm
from CombineMols.CombineMols import CombineMols
from rdkit.Chem import Draw

from rdkit.Chem import AllChem
from rdkit.Chem.Draw import IPythonConsole
from rdkit.Chem.Draw import MolDrawing, DrawingOptions

import time
import os
from PIL import Image
import pandas as pd
import csv




DrawingOptions.bondLineWidth=1.8
DrawingOptions.atomLabelFontSize=14
DrawingOptions.includeAtomNumbers=True

datapath = './data_pyg/prediction/CO2/'

def get_connection_info(mol=None, symbol="*") -> Dict:
    """Get connection information a PSMILES string.

    Args:
        mol (Chem.RWMol, optional): _description_. Defaults to None.
        symbol (str, optional): _description_. Defaults to "*".

    Returns:
        Dict: Dictionary containing information of the mol
    """   

    ret_dict = {}

    stars_indices, stars_type, all_symbols, all_index = [], [], [], []
    for star_idx, atom in enumerate(mol.GetAtoms()):
        all_symbols.append(atom.GetSymbol())
        all_index.append(atom.GetIdx())
        if symbol in atom.GetSymbol():
            stars_indices.append(star_idx)
            stars_type.append(atom.GetSmarts())

    num_of_stars = len(stars_indices)
    if num_of_stars < 2:
        return {}
    
    stars_bond = mol.GetBondBetweenAtoms(stars_indices[0], stars_indices[1])
    if stars_bond:
        stars_bond = stars_bond.GetBondType()

    ret_dict["symbols"] = all_symbols
    ret_dict["index"] = all_index

    ret_dict["star"] = {
        "index": stars_indices,
        "atom_type": stars_type,
        "bond_type": stars_bond,
    }

    # multiple neighbors are possible
    neighbor_indices = []
    for i in range(num_of_stars):
        neighbor_indices.append([x.GetIdx() for x in mol.GetAtomWithIdx(stars_indices[i]).GetNeighbors()])
        #[x.GetIdx() for x in mol.GetAtomWithIdx(stars_indices[1]).GetNeighbors()],

    neighbors_type = []
    for i in range(num_of_stars):
        neighbors_type.append([mol.GetAtomWithIdx(x).GetSmarts() for x in neighbor_indices[0]])

    # Bonds between stars and neighbors
    neighbor_bonds = []
    for i in range(num_of_stars):
        neighbor_bonds.append([mol.GetBondBetweenAtoms(stars_indices[i], x).GetBondType()
                               for x in neighbor_indices[i]])
                              
    s_path = None
    if neighbor_indices[0][0] != neighbor_indices[1][0]:
        s_path = Chem.GetShortestPath(
            mol, neighbor_indices[0][0], neighbor_indices[1][0]
        )

    ret_dict["neighbor"] = {
        "index": neighbor_indices,
        "atom_type": neighbors_type,
        "bond_type": neighbor_bonds,
        "path": s_path,
    }

    # Stereo info
    stereo_info = []
    for b in mol.GetBonds():
        bond_type = b.GetStereo()
        if bond_type != Chem.rdchem.BondStereo.STEREONONE:
            idx = [b.GetBeginAtomIdx(), b.GetEndAtomIdx()]
            neigh_idx = b.GetStereoAtoms()
            stereo_info.append(
                {
                    "bond_type": bond_type,
                    "atom_idx": idx,
                    "bond_idx": b.GetIdx(),
                    "neighbor_idx": list(neigh_idx),
                }
            )

    ret_dict["stereo"] = stereo_info

    # Ring info
    ring_info = mol.GetRingInfo()
    ret_dict["atom_rings"] = ring_info.AtomRings()
    ret_dict["bond_rings"] = ring_info.BondRings()
    #print(ret_dict)
    return ret_dict

def get_mol(psmiles) -> Chem.RWMol:
    """Returns a RDKit mol object.

    Note:
        In jupyter notebooks, this function draws the SMILES string

    Returns:
        Chem.MolFromSmiles: Mol object
    """
    return Chem.RWMol(Chem.MolFromSmiles(psmiles))

def edit_mol(ori_psmiles, des_psmiles) -> str:
    start_mol, des_mol = get_mol(ori_psmiles), get_mol(des_psmiles)
    #Draw.MolToFile(start_mol, 'images/start_mol.png')

    # Stitch these together is to make an editable copy of the molecule object
    combo = Chem.CombineMols(start_mol,des_mol)
    comboSmile = Chem.MolToSmiles(combo)
    #print(f"Combo SMILES: {comboSmile}\n")
    #print(Chem.MolToMolBlock(combo))
    
    # Obtain connection info for future bonds/atoms remove/add
    info = get_connection_info(combo)
    if not info:
        print("************************** No Star Mark! **************************")
        return des_psmiles

    #print(f"Combo Info: {info}\n")
    #Draw.MolToFile(combo, 'images/combo.png')
    edcombo = Chem.EditableMol(combo)
    staridx1, staridx2 = 0, -1
    edcombo.AddBond(
            info["neighbor"]["index"][staridx1][0],
            info["neighbor"]["index"][staridx2][0],
            info["neighbor"]["bond_type"][staridx1][0],
        )
    edcombo.RemoveBond(info["star"]["index"][staridx1], info["neighbor"]["index"][staridx1][0])
    edcombo.RemoveBond(info["star"]["index"][staridx2], info["neighbor"]["index"][staridx2][0])
    edcombo.RemoveAtom(info["star"]["index"][staridx2])
    edcombo.RemoveAtom(info["star"]["index"][staridx1])
    back = edcombo.GetMol()
    backSmile = Chem.MolToSmiles(back)
        #print(f"Back SMILES: {backSmile}\n")
    return backSmile
    
    #backSmile = set()
    #for idx in range(num_stars):
     #   ed_res = edAtomBond(Chem.EditableMol(combo), idx, idx+num_stars)
      #  ed_res_smile = Chem.MolToSmiles(ed_res)
       # if ed_res_smile not in backSmile:
        #    backSmile.add(ed_res_smile)
            #Draw.MolToFile(ed_res, 'images/edit_%s.png'%ed_res_smile)
    #return list(backSmile)

#def dfs()

def direct_edit_mol(ori_psmiles, des_psmiles) -> str:
    ori_psmiles = ori_psmiles.replace("*", "I")
    des_psmiles = ori_psmiles
    mol_rep = CombineMols(ori_psmiles, des_psmiles, "I")
    backSmile = []
    seen = set()
    for i in range(len(mol_rep)):
        j = Chem.MolToSmiles(mol_rep[i])
        if j not in seen:
            seen.add(j)
            moll = j.replace("I","*")
            print(f"SMILES: {moll}\n")
            backSmile.append(moll)
            Draw.MolToFile(mol_rep[i], 'direct_edit_%s.png'%moll)
    
    return backSmile
def star_edge(ori_psmiles) -> str:
    ori_mol = get_mol(ori_psmiles)
    info = get_connection_info(ori_mol)
    print(info)
    if not info:
        print("************************** No Star Mark! **************************")
        return ori_psmiles
    edsmiles = Chem.EditableMol(ori_mol)
    staridx1, staridx2 = 0, -1
    # see if the neighbors of stars are already bonded with each other
    # can not replace star as an edge
    neighidx1, neighidx2 =   info["neighbor"]["index"][staridx1][0],info["neighbor"]["index"][staridx2][0]
    path = list(info["neighbor"]['path'])
    for i in range(len(path)):
        if i<len(path)-1:
            if (path[i] == neighidx1 and path[i+1] == neighidx2) or (path[i] == neighidx2 and path[i+1] == neighidx1):
                return ''
        
    edsmiles.AddBond(
            info["neighbor"]["index"][staridx1][0],
            info["neighbor"]["index"][staridx2][0],
            info["neighbor"]["bond_type"][staridx1][0],
        )
    edsmiles.RemoveBond(info["star"]["index"][staridx1], info["neighbor"]["index"][staridx1][0])
    edsmiles.RemoveBond(info["star"]["index"][staridx2], info["neighbor"]["index"][staridx2][0])
    edsmiles.RemoveAtom(info["star"]["index"][staridx2])
    edsmiles.RemoveAtom(info["star"]["index"][staridx1])
    back = edsmiles.GetMol()
    backSmile = Chem.MolToSmiles(back)
        #print(f"Back SMILES: {backSmile}\n")
    return backSmile
def dfs(psmiles, n) -> str:
    n = int(n)
    if n == 2:
        mol = edit_mol(psmiles, psmiles)
        return mol
    elif n == 1:
        return psmiles
    else:
        if n%2 != 0:
            return edit_mol(dfs(psmiles, n-1), psmiles)
        else:
            return edit_mol(dfs(psmiles, n//2), dfs(psmiles, n//2))
        
if __name__=='__main__':
    ocur_times = 0

    smiles = '[H]C1CC(*)CC1\C=C\*'
    res = star_edge(smiles)
    print(res)
    # Save New Stucture Images


    mol = get_mol(res)
    # Use direct edit
    #Draw.MolToFile(mol, newpath+'/d_%s.png'%i)
    Draw.MolToFile(mol, 'res_img/polymers/%s_res.png'%ocur_times)
           

    print("************************** Editing is done! **************************")


