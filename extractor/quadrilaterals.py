"""Crops and rectifies segmented PV modules.

This module is used to crop out and rectify an image patch for every segmented
PV module in an IR video frame. Patches are generated from 16-bit radiometric
TIFFs. The procedure for creating a single patch is as follows:

1) Load binary segmentation mask of the PV module
2) Compute the contour and convex hull of the mask
3) Find the approximately smallest enclosing quadrilateral of the convex hull
4) If the IoU between convex hull and quadrilaterl is lower than a specified
   threshold abort the procedure and do not crop out this PV module
5) Else, sort the corner points of the quadrilateral in CW order
6) Compute the maximum width and height of the quadrilateral
7) Compute a homography from the corners of the quadrilateral to a rectangular
   destination image with the previously computed width and height
8) Project the image region inside the quadrilateral onto the rectangular
   destination image using the computed homography
9) If the width is larger than the height, rotate the rectangular patch by 90
   degrees CCW
"""

import os
import glob
import csv
import pickle
import logging
from tqdm import tqdm
import numpy as np
import cv2

from extractor.common import Capture, delete_output, sort_cw, \
    contour_and_convex_hull, compute_mask_center, \
    get_immediate_subdirectories, line, line_intersection


logger = logging.getLogger(__name__)


def findEnclosingPolygon(convex_hull, num_vertices=4, visu=False):
    """Computes the enclosing k-polygon of a convex shape.

    The algorithm works as follows:

    While number of edges > N do:
        remove the shortest edge by replacing its endpoints with the
        intersection point of the adjacent edges

    Source: https://stackoverflow.com/questions/11602259/find-the-smallest-
            containing-convex-polygon-with-a-given-number-of-points

    Args:
        convex_hull (`numpy.ndarray`): Shape [-1, 0, 2] of dtype int32. The
            convex hull of the polygon as returned by `cv2.convexHull` with
            `clockwise = False` and `returnPoints = True`.

        num_vertices (`int`): Number of vertices of the returned enclosing
            polygon.

    Returns:
        Enclosing polygon (`numpy.ndarray`) of shape [num_vertices, 0, 2] and
        dtype int32.
    """
    hull = np.copy(convex_hull)
    while len(hull) > num_vertices:
        # get shortest edge
        edge_lenghts = []
        for i in range(0, hull.shape[0]-1):
            edge_lenght = np.linalg.norm(
                hull[i, 0, :] - hull[i+1, 0, :], axis=-1)
            edge_lenghts.append(edge_lenght)
        edge_lenghts.append(np.linalg.norm(
            hull[-1, 0, :] - hull[0, 0, :], axis=-1))
        # point in hull where shortest edge starts
        min_edge_idx = np.argmin(edge_lenghts)
        #print("Removing hull point {}".format(min_edge_idx))

        # get indices of hull points which form the two adjacent edges
        n = len(hull)
        previous_edge_idx = ((min_edge_idx-1)%n, min_edge_idx%n)
        subsequent_edge_idx = ((min_edge_idx+1)%n, (min_edge_idx+2)%n)

        # compute intersection between adjacent edges
        edge_previous = line(list(hull[previous_edge_idx[0], 0, :]), list(
            hull[previous_edge_idx[1], 0, :]))
        edge_subsequent = line(list(hull[subsequent_edge_idx[0], 0, :]), list(
            hull[subsequent_edge_idx[1], 0, :]))
        has_intersection, intersection = line_intersection(
            edge_previous, edge_subsequent)
        #print(intersection)

        # if lines do not intersect (they are parallel) use the middle point instead
        if not has_intersection:
            #print("No intersection, using mean")
            intersection = np.mean(np.vstack((hull[previous_edge_idx[1], 0, :],
                hull[subsequent_edge_idx[0], 0, :])), axis=0)
            #print(intersection)

        # replace endpoints of shortest edge with computed intersection
        hull[min_edge_idx, 0, :] = np.array(
            [round(intersection[0]), round(intersection[1])])
        hull = np.delete(hull, (min_edge_idx+1)%len(hull), axis=0)

        # ensure that new hull is convex
        hull_tmp = cv2.convexHull(hull, clockwise=False, returnPoints=True)
        if len(hull_tmp) > num_vertices:
            hull = hull_tmp
    return hull


def compute_iou(convex_hull, quadrilateral):
    """Computes the IoU of the convex hull and
    the estimated bounding quadrilateral."""
    intersect_area, _p12 = cv2.intersectConvexConvex(convex_hull, quadrilateral)
    iou = intersect_area / cv2.contourArea(quadrilateral)
    return iou


def load_tracks(tracks_file):
    """Load Tracks CSV file."""
    tracks = {}
    with open(tracks_file, newline='', encoding="utf-8-sig") as csvfile:
        dialect = csv.Sniffer().sniff(csvfile.readline(), delimiters=",;")
        csvfile.seek(0)
        csvreader = csv.reader(csvfile, dialect)
        for row in csvreader:
            frame_name, mask_name, track_id, _, _ = row
            tracks[(frame_name, mask_name)] = track_id
    return tracks


def run(frames_root, inference_root, tracks_root, output_dir, min_iou):

    delete_output(output_dir)
    os.makedirs(output_dir, exist_ok=True)

    # load frames & masks
    frame_files = sorted(
        glob.glob(os.path.join(frames_root, "radiometric", "*.tiff")))
    mask_dirs = sorted(get_immediate_subdirectories(
        os.path.join(inference_root, "masks")))
    mask_files = [sorted(glob.glob(os.path.join(inference_root, 
        "masks", r, "*.png"))) for r in mask_dirs]

    # load track file
    tracks_file = os.path.join(tracks_root, "tracks.csv")
    tracks = load_tracks(tracks_file)

    cap = Capture(frame_files, mask_files)

    quadrilaterals = {}

    pbar = tqdm(total=len(frame_files))
    while True:
        frame, masks, frame_name, mask_names = \
            cap.get_next_frame(preprocess=False)
        if frame is None:
            break

        # get minimum enclosing quadrilateral for each mask
        # (and compute mean IoU for all masks in the frame)
        quads = []
        centers = []
        mask_names_filtered = []
        for mask, mask_name in zip(masks, mask_names):
            convex_hull, contour = contour_and_convex_hull(mask)
            center = compute_mask_center(convex_hull, contour, method=1)
            quad = findEnclosingPolygon(convex_hull, num_vertices=4)
            iou = compute_iou(convex_hull, quad)
            if iou > min_iou:
                quads.append(quad)
                centers.append(center)
                mask_names_filtered.append(mask_name)

        # save quadrilaterals
        # TODO: use JSON file instead of pkl file (note dependencies in PV-Drone-Inspect-Viewer)
        for quad, center, mask_name in zip(
            quads, centers, mask_names_filtered):
            
            module_id = tracks[(frame_name, mask_name)]
            quadrilaterals[(module_id, frame_name, mask_name)] = {
                "quadrilateral": sort_cw(quad),
                "center": center,
            }

        pbar.update(1)
    pbar.close()

    # save meta file
    pickle.dump(quadrilaterals, open(os.path.join(output_dir, "quadrilaterals.pkl") , "wb"))
