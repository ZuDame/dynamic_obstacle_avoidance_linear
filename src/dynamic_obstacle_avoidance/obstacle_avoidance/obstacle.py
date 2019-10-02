import numpy as np
from math import sin, cos, pi, ceil
import warnings, sys


import numpy as np
import numpy.linalg as LA

from dynamic_obstacle_avoidance.obstacle_avoidance.modulation import *

import matplotlib.pyplot as plt

visualize_debug = False

def get_orthogonal_basis(vector, normalize=False):
    if not type(vector) == np.ndarray:
        vector = np.array(vector)
        
    if normalize:
        v_norm = LA.norm(vector)
        if v_norm:
            vector = vector / v_norm
        
    dim = vector.shape[0]

    Basis_Matrix = np.zeros((dim, dim))
    
    if dim == 2:
        Basis_Matrix[:, 0] = vector
        Basis_Matrix[:, 1] = np.array([Basis_Matrix[1, 0],
                                       -Basis_Matrix[0, 0]])
        
    if dim > 2:
        warnings.warn("Implement higher dimensionality than d={}".format(dim))

    return Basis_Matrix


def get_directional_weighted_sum(reference_direction, directions, weights, normalize=True, normalize_reference=True, obs=[], position=[]):
    # TODO remove obs and position
    # Move to different file
    ind_nonzero = (weights>0)

    reference_direction = np.copy(reference_direction)
    directions = directions[:, ind_nonzero]
    weights = weights[ind_nonzero]

    # TODO remove obs from arguments after debugging
    n_directions = weights.shape[0]
    if n_directions<=1:
        return directions[:, 0]
        
    dim = np.array(reference_direction).shape[0]

    # Create copy to avoid changing initial values
    
    if visualize_debug and False:
        ref_abs = obs.transform_relative2global_dir(reference_direction)
        
        position = obs.transform_relative2global(reference_direction)
        plt.quiver(position[0], position[1], ref_abs[0], ref_abs[1], color='g', label='Reference')

        dir_abs = np.zeros((dim, n_directions))
        for ii in range(n_directions):
            dir_abs[:, ii] = obs.transform_relative2global_dir(directions[:,ii])
            plt.quiver(position[0], position[1], dir_abs[0,ii], dir_abs[1,ii], color='b', label='Normal')

    if normalize_reference:
        norm_refDir = LA.norm(reference_direction)
        if norm_refDir:
            reference_direction /= norm_refDir

     # TODO - higher dimensions
    if normalize:
        norm_dir = LA.norm(directions, axis=0)
        ind_nonzero = (norm_dir>0)
        directions[:,ind_nonzero] = directions[:,ind_nonzero]/np.tile(norm_dir[ind_nonzero], (dim, 1))

    OrthogonalBasisMatrix = get_orthogonal_basis(reference_direction)

    directions_referenceSpace = np.zeros(np.shape(directions))
    for ii in range(np.array(directions).shape[1]):
        directions_referenceSpace[:,ii] = OrthogonalBasisMatrix.T.dot( directions[:,ii])

    directions_directionSpace = directions_referenceSpace[1:, :]

    norm_dirSpace = LA.norm(directions_directionSpace, axis=0)
    ind_nonzero = (norm_dirSpace > 0)
    
    directions_directionSpace[:,ind_nonzero] = (directions_directionSpace[:, ind_nonzero] /  np.tile(norm_dirSpace[ind_nonzero], (dim-1, 1)))

    # Do not check cosinus, since normalization happened
    # TODO check why low, and remove

    cos_directions = directions_referenceSpace[0,:]
    if np.sum(cos_directions > 1) or np.sum(cos_directions < -1):
        cos_directions = np.min(np.vstack((cos_directions, np.ones(n_directions))), axis=0)
        cos_directions = np.max(np.vstack((cos_directions, -np.ones(n_directions))), axis=0)
        warnings.warn("Cosinus value out of bound.")
        
    directions_directionSpace *= np.tile(np.arccos(cos_directions), (dim-1, 1))
    direction_dirSpace_weightedSum = np.sum(directions_directionSpace*
                                            np.tile(weights, (dim-1, 1)), axis=1)

    norm_directionSpace_weightedSum = LA.norm(direction_dirSpace_weightedSum)
    if norm_directionSpace_weightedSum:
        direction_weightedSum = (OrthogonalBasisMatrix.dot(
                                  np.hstack((np.cos(norm_directionSpace_weightedSum),
                                              np.sin(norm_directionSpace_weightedSum) / norm_directionSpace_weightedSum * direction_dirSpace_weightedSum)) ))
    else:
        direction_weightedSum = OrthogonalBasisMatrix[:,0]
    
    return direction_weightedSum

class Obstacle:
    """ Class of obstacles """
    def __init__(self,  orientation=0, th_r=None, sf=1, delta_margin=0, xd=[0,0], sigma=1,  w=0, x_start=0, x_end=0, timeVariant=False, a=[1,1], p=[1,1], x0=None, center_position=[0,0],  tail_effect=True, always_moving=True, axes_length=None, is_boundary=False, Gamma_ref=0):
        # This class defines obstacles to modulate the DS around it
        # At current stage the function focuses on Ellipsoids, but can be extended to more general obstacles
        
        # Leave at the moment for backwards compatibility
        if type(axes_length) == type(None):
            self.a = a
            self.axes = np.array(a)
            self.axes_length = np.array(a)
        else:
            self.axes_length = axes_length
            self.axes = np.array(axes_length)
            self.a = axes_length

        self.margin_axes =  self.axes*np.array(sf)+np.array(delta_margin)
        
        self.p = np.array(p)
        self.sf = sf
        self.sigma = sigma
        self.tail_effect = tail_effect # Modulation if moving away behind obstacle

        # Obstacle attitude
        if type(x0) != type(None):
            center_position = x0 # TODO remove and rename
        self.center_position = center_position
        self.x0 = center_position

        if type(th_r)!= type(None):
            orientation = th_r
        self.th_r = orientation # TODO -- remove
        self.orientation = orientation
        
        self.d = len(self.center_position) #Dimension of space # TODO remove
        self.dim = len(self.center_position) #Dimension of space
        
        self.rotMatrix = []
        self.compute_R() # Compute Rotation Matrix
        
        self.resolution = 0 #Resolution of drawing
        
        self.x_obs = [] # Numerical drawing of obstacle boundarywq
        self.x_obs_sf = [] # Obstacle boundary plus margin!

        self.timeVariant = timeVariant
        if self.timeVariant:
            self.func_xd = 0
            self.func_w = 0
            
        else:
            self.always_moving = always_moving
        
        if sum(np.abs(xd)) or w or self.timeVariant:
            # Dynamic simulation - assign varibales:
            self.x_start = x_start
            self.x_end = x_end
            self.always_moving = False
        else:
            self.x_start = 0
            self.x_end = 0
            
        self.w = w # Rotational velocity
        self.xd = xd #

        # Relative Reference point // Dyanmic center
        # self.reference_point = self.center_position # TODO remove and rename
        self.reference_point = np.zeros(self.dim) # TODO remove and rename
        self.center_dyn = self.reference_point # TODO remove and rename

        self.reference_point_is_inside = True

        self.Gamma_ref = Gamma_ref
        self.is_boundary = is_boundary

    # def update_reference(self, new_ref):
        # TODo write function
    
    def transform_global2relative(self, position=None, direction=None): # Inherit
            return self.rotMatrix.T .dot(position - np.array(self.center_position))

    def transform_relative2global(self, position=None): # TODO - inherit
        return (self.rotMatrix.dot(position))  + np.array(self.center_position)
        
    def transform_relative2global_dir(self, direction=None): # TODO - inherit
        return self.rotMatrix.dot(direction)

    def transform_global2relative_dir(self, direction=None): # TODO - inherit
        return self.rotMatrix.T.dot(direction)

    def extend_hull_around_reference(self, edge_reference_dist=0.2):
        # TODO add margin

        vec_cent2ref = np.array(self.get_reference_point(in_global_frame=False))
        dist_cent2ref = LA.norm(vec_cent2ref)
        
        self.hull_edge = vec_cent2ref*(1 + edge_reference_dist*np.min(self.axes_length)/dist_cent2ref)
        # self.hull_edge =  np.array(self.get_reference_point(in_global_frame=False))

        # Intersection of (x_1/a_1)^2 + (x_2/a_2)^2 = 1 & x_2=m*x_1+c
        # Solve for determinant D=0 (tangent with only one intersection point)
        A_ =  self.hull_edge[0]**2 - self.axes[0]**2
        B_ = -2*self.hull_edge[0]*self.hull_edge[1]
        C_ = self.hull_edge[1]**2 - self.axes[1]**2
        D_ = B_**2 - 4*A_*C_

        m = [0, 0]

        m[1] = (-B_ - np.sqrt(D_)) / (2*A_)
        m[0] = (-B_ + np.sqrt(D_)) / (2*A_)
        
        self.tangent_points = np.zeros((self.dim, 2))
        self.normal_vector = np.zeros((self.dim, 2))
        self.tangent_vector = np.zeros((self.dim, 2))
        self.normalDistance2center = np.zeros(2)

        for ii in range(2):
            c = self.hull_edge[1] - m[ii]*self.hull_edge[0]

            A = (self.axes[0]*m[ii])**2 + self.axes[1]**2
            B = 2*self.axes[0]**2*m[ii]*c
            # D != 0 so C not interesting

            self.tangent_points[0, ii] = -B/(2*A)
            self.tangent_points[1, ii] = m[ii]*self.tangent_points[0, ii] + c

            self.tangent_vector[:,ii] = self.tangent_points[:, ii]-self.hull_edge
            self.tangent_vector[:,ii] /= LA.norm(self.tangent_vector[:,ii])
            
            self.normal_vector[:, ii] = np.array([self.tangent_vector[1,ii],
                                                  -self.tangent_vector[0,ii]]) 
            # Check direction
            self.normalDistance2center[ii] = self.normal_vector[:, ii].T.dot(self.hull_edge)

            if (self.normalDistance2center[ii] < 0):
                self.normal_vector[:, ii] = self.normal_vector[:, ii]*(-1)
                self.normalDistance2center[ii] *= -1

        if False:
            # plt.plot()
            for ii in range(2):
                norm_abs = self.transform_relative2global_dir(self.normal_vector[:,ii])
                plt.quiver(0,0, norm_abs, norm_abs, color='y', label='Normal')

            
    def set_reference_point(self, position, in_global_frame=False): # Inherit
        if in_global_frame:
            position = self.transform_global2relative(position)
        self.reference_point = position
        self.center_dyn = self.reference_point

        if self.get_gamma(self.reference_point)>1:
            self.extend_hull_around_reference()
            self.reference_point_is_inside = False
            
        else:
            self.reference_point_is_inside = True

    def are_lines_intersecting(self, direction_line, passive_line):
        # solve equation line1['point_start'] + a*line1['direction'] = line2['point_end'] + b*line2['direction']
        connection_direction = np.array(direction_line['point_end']) - np.array(direction_line['point_start']) 
        connection_passive = np.array(passive_line['point_end']) - np.array(passive_line['point_start']) 
        connection_matrix = np.vstack((connection_direction, -connection_passive)).T

        if LA.det(connection_matrix): # nonzero value
            direction_factors = (LA.inv(connection_matrix) @
                                 (np.array(passive_line['point_start'])
                                  - np.array(direction_line['point_start']) ))
        
            # Smooth because it's a tangent
            if direction_factors[0]>=0:
                if direction_factors[1]>=0 and LA.norm(direction_factors[1]*connection_passive) <= LA.norm(connection_passive):
                    
                    return True, LA.norm(direction_factors[0]*connection_direction)
        
        if False: # show plot
            dir_start = self.transform_relative2global(direction_line['point_start'])
            dir_end = self.transform_relative2global(direction_line['point_end'])

            pas_start = self.transform_relative2global(passive_line['point_start'])
            pas_end = self.transform_relative2global(passive_line['point_end'])
            
            plt.ion()
            plt.plot([dir_start[0], dir_end[0]], [dir_start[1], dir_end[1]], 'g--')
            plt.plot([pas_start[0], pas_end[0]], [pas_start[1], pas_end[1]], 'r--')
            plt.show()
            print('done intersections')
            
        return False, -1
        

    def get_obstacle_radius(self, position, in_global_frame=False, Gamma=None): # Inherit
        if in_global_frame:
            position = self.transform_global2relative(position)

        if not Gamma==None:
            Gamma = self.get_gamma(position)
        dist_to_center = LA.norm(position)

        return dist_to_center/Gamma

    def get_reference_point(self, in_global_frame=False): # Inherit
        if in_global_frame:
            return self.transform_relative2global(self.reference_point)
        else:
            return self.reference_point
        
    def get_gamma(self, position, in_global_frame=False):
        if not type(position)==np.ndarray:
            position = np.array(position)

        # Rename
        if in_global_frame:
            position = self.transform_global2relative(position)

        if not self.reference_point_is_inside:
            for ii in np.arange(self.tangent_points.shape[1]):
                reference_line = {"point_start":[0,0], "point_end":position}
                
                # TODO - don't use reference point, but little 'offset' to avoid singularity
                tangent_line = {"point_start":self.hull_edge,
                                "point_end":self.tangent_points[:, ii]}
                
                ind_intersect, dist_intersect = self.are_lines_intersecting(reference_line, tangent_line)
                if ind_intersect:
                    return LA.norm(position)/dist_intersect

        # Original Gamma
        Gamma = np.sum((position/self.margin_axes)**(2*self.p)) # distance
        
        if self.is_boundary:
            Gamma = self.get_boundaryGamma(Gamma,Gamma_ref=self.Gamma_ref)
        # print('Gamma', Gamma)
        return Gamma

    def get_boundaryGamma(self, Gamma, Gamma_ref=0):
        if Gamma <= Gamma_ref:
            return sys.float_info.max
        else:
            return (1-Gamma_ref)/(Gamma-Gamma_ref)
        

    def get_distance_to_hullEdge(self, position):
        n_planes = self.normal_vector.shape[1]
        if len(self.hull_edge.shape)<2:
            vec_position2edge = np.tile(position-self.hull_edge, (n_planes, 1)).T
        else:
            vec_position2edge = np.tile(position, (n_planes, 1)).T - self.hull_edge
        distance2plane = np.sum((self.normal_vector * vec_position2edge), axis=0)

        if False:
            vec_position2edge = np.tile(position, (n_planes, 1)).T - self.tangent_points
            distance2plane = np.sum((self.normal_vector * vec_position2edge), axis=0)
                
        return distance2plane
    

    def get_angle2dir(self, position_dir, tangent_dir, needs_normalization=True):
        if needs_normalization:
            if len(position_dir.shape) > 1:
                position_dir /= np.tile(LA.norm(position_dir,axis=0), (self.dim, 1))
                tangent_dir /= np.tile(LA.norm(tangent_dir, axis=0), (self.dim, 1))
                angle_arccos = np.sum(position_dir * tangent_dir, axis=0)
            else:
                position_dir /= LA.norm(position_dir)
                tangent_dir /= LA.norm(tangent_dir)
                angle_arccos = np.sum(position_dir * tangent_dir)
        return np.arccos(angle_arccos)
        
        
    def get_angle2referencePatch(self, position, max_angle=pi):
        # angle between 0 and pi
        n_planes = self.normal_vector.shape[1]

        vec_position2edge = np.tile(position-self.hull_edge, (n_planes, 1)).T
        distance2plane = np.sum((self.normal_vector*vec_position2edge), axis=0)

        angle2refencePatch = np.ones(n_planes)*max_angle
        
        for ii in range(n_planes):
            if distance2plane[ii]<0:
                continue

            vec_position2edge[:, ii] /= LA.norm(vec_position2edge[:, ii])

            cos_position2edge = vec_position2edge[:, ii].T @ self.tangent_vector[:,ii]
            angle2refencePatch[ii] = np.arccos(cos_position2edge)

        if False:
            cos_tangs = np.sum(self.tangent_vector[:,0].T @ self.tangent_vector[:,1])
            print('angle', np.arccos(cos_tangs))
        
        return angle2refencePatch
    
            
    def get_angle_weight(self, weights, max_weight=pi, min_weight=0, check_range=False):
        n_weights = np.array(weights).shape[0]

        if check_range:
            weights = np.min(np.vstack((weights, np.ones(n_weights)*max_weight)) )
            weights = np.max(np.vstack((weights, np.ones(n_weights)*min_weight)) )

        weights = (max_weight-weights)/(max_weight-min_weight)
        weight_norm = np.sum(weights)

        if weight_norm:
            return weights/weight_norm
        return weights

    
    def get_distance_weight(self, distance, power=1):
        ind_positiveDistance = (distance>0)

        weights = np.zeros(distance.shape)
        weights[ind_positiveDistance] = (1./distance[ind_positiveDistance])**power
        weights[ind_positiveDistance] /= np.sum(weights[ind_positiveDistance])
        # weights[~ind_positiveDistance] = 0

        return weights
        
    def get_normal_direction(self, position, in_global_frame=False, normalize=True):
        
        if in_global_frame:
            position = self.transform_global2relative(position)
            
        if not self.reference_point_is_inside:
            ind_intersect = np.zeros(self.normalDistance2center.shape, dtype=bool)
            
            distances2plane = self.get_distance_to_hullEdge(position)
            
            ind_outside = (distances2plane > 0)
            
            if np.sum(ind_outside)>0:
                for ii in np.arange(ind_outside.shape[0])[ind_outside]:
                    
                    reference_line = {"point_start":[0,0],
                                      "point_end":position}
                    # TODO - don't use reference point, but little 'offset' to avoid singularity
                    tangent_line = {"point_start":self.hull_edge,
                                    "point_end":self.tangent_points[:, ii]}
                    
                    ind_intersect[ii], dist = self.are_lines_intersecting(reference_line, tangent_line)
                    
                    if ind_intersect[ii]:
                        break
                
                if np.sum(ind_intersect): # nonzero
                    angle2referencePlane = self.get_angle2referencePatch(position)
                    weights = self.get_angle_weight(angle2referencePlane)
                    
                    try:
                        normal_vector = get_directional_weighted_sum(reference_direction=position, directions=self.normal_vector, weights=weights, normalize=False, obs=self, position=position, normalize_reference=True)
                        
                    except:
                        # pass
                        import pdb; pdb.set_trace() ## DEBUG ##
                    # return normal_vector
        
        if self.reference_point_is_inside or np.sum(ind_intersect)==0:
        # Elsee
            normal_vector = (2*self.p/self.margin_axes*(position/self.margin_axes)**(2*self.p - 1))
        
        if normalize:
            normal_vector = normal_vector/LA.norm(normal_vector)

        if False:
            self.draw_reference_hull(normal_vector, position)

        # print('angle', angle2referencePlane)
        # print('weight', weights)
        # print('normal', normal_vector)
        # print('\n')

        return normal_vector

    def draw_reference_hull(self, normal_vector, position):
        pos_abs = self.transform_relative2global(position)
        norm_abs = self.transform_relative2global_dir(normal_vector)
        
        plt.quiver(pos_abs[0], pos_abs[1], norm_abs[0], norm_abs[1], color='k', label="Normal")

        ref_dir = self.transform_relative2global_dir(self.get_reference_direction(position, in_global_frame=False, normalize=True))
        
        plt.quiver(pos_abs[0], pos_abs[1], ref_dir[0], ref_dir[1], color='g', label="Reference")

        ref_abs = self.transform_relative2global(self.hull_edge)
        
        for ii in range(2):
            tang_abs = self.transform_relative2global(self.tangent_points[:, ii])
            plt.plot([tang_abs[0], ref_abs[0]], [tang_abs[1], ref_abs[1]], 'k--')

        # plt.ion()
        # plt.show()

    def get_reference_direction(self, position, in_global_frame=False, normalize=True):
        # Inherit
        if in_global_frame:
            position = self.transform_global2relative(position)
            
        if hasattr(self, 'reference_point') or hasattr(self,'center_dyn'):  # automatic adaptation of center 
            reference_direction = - (position-self.reference_point)
        else:
            reference_direction = - position

        if normalize:
            ref_norm = LA.norm(reference_direction)
            if ref_norm:
                return reference_direction/ref_norm

        return reference_direction

    def update_pos(self, t, dt, x_lim=[], y_lim=[]):
        # Inherit
        # TODO - implement function dependend movement (yield), nonlinear integration
        # First order Euler integration

        if self.always_moving or self.x_end > t :
            if self.always_moving or self.x_start<t:
                # Check if xd and w are functions
                if self.timeVariant:
                    # TODO - implement RK4 for movement
                    
                    self.xd = self.func_xd(t)
                    self.w = self.func_w(t)

                self.center_position = [self.center_position[i] + dt*self.xd[i] for i in range(self.d)] # update position

                if len(x_lim):
                    self.center_position[0] = np.min([np.max([self.center_position[0], x_lim[0]]), x_lim[1]])
                if len(y_lim):
                    self.center_position[1] = np.min([np.max([self.center_position[1], y_lim[0]]), y_lim[1]])

                if self.w: # if new rotation speed

                    if self.d <= 2:
                        self.th_r = self.th_r + dt*self.w  #update orientation/attitude
                    else:
                        self.th_r = [self.th_r[i]+dt*self.w[i] for i in range(self.d)]  #update orientation/attitude
                    self.compute_R() # Update rotation matrix
                
                self.draw_obstacle()
            

    def draw_ellipsoid(self, *args, **kwargs):
        # TODO remove
        warnings.warn("<<draw_ellipsoid>> has been renamed <<draw_obstacle>>")
        self.draw_obstacle(*args, **kwargs)
        # sys.exit(0)
        
    def draw_obstacle(self, numPoints=20, a_temp = [0,0], draw_sfObs = False):
        if self.d == 2:
            theta = np.linspace(-pi,pi, num=numPoints)
            resolution = numPoints # Resolution of drawing #points
            
        else:
            numPoints = [numPoints, ceil(numPoints/2)]
            theta, phi = np.meshgrid(np.linspace(-pi,pi, num=numPoints[0]),np.linspace(-pi/2,pi/2,num=numPoints[1]) ) #
            numPoints = numPoints[0]*numPoints[1]
            resolution = numPoints # Resolution of drawing #points
            theta = theta.T
            phi = phi.T
        
        # For an arbitrary shap, the next two lines are used to find the shape segment
        if hasattr(self,'partition'):
            warnings.warn('Warning - partition no finished implementing')
            for i in range(self.partition.shape[0]):
                ind[i,:] = self.theta>=(self.partition[i,1]) & self.theta<=(self.partition[i,1])
                [i, ind]=max(ind)
        else:
            ind = 0

        if sum(a_temp) == 0:
            a = self.a
        else:
            a = a_temp
            
        p = self.p[:]

        R = np.array(self.rotMatrix)

        x_obs = np.zeros((self.d, numPoints))
        
        if self.d == 2:
            x_obs[0,:] = a[0]*np.cos(theta)
            x_obs[1,:] = np.copysign(a[1], theta)*(1 - np.cos(theta)**(2*p[0]))**(1./(2.*p[1]))
        else:
            x_obs[0,:] = (a[0]*np.cos(phi)*np.cos(theta)).reshape((1,-1))
            x_obs[1,:] = (a[1]*np.copysign(1, theta)*np.cos(phi)*(1 - np.cos(theta)**(2*p[0]))**(1./(2.*p[1]))).reshape((1,-1))
            x_obs[2,:] = (a[2]*np.copysign(1,phi)*(1 - (np.copysign(1,theta)*np.cos(phi)*(1 - 0 ** (2*p[2]) - np.cos(theta)**(2*p[0]))**(1/(2**p[1])))**(2*p[1]) - (np.cos(phi)*np.cos(theta)) ** (2*p[0])) ** (1/(2*p[2])) ).reshape((1,-1))
        
        x_obs_sf = np.zeros((self.d,numPoints))
        if not hasattr(self, 'sf'):
            self.sf = 1
            
        if type(self.sf) == int or type(self.sf) == float:
            x_obs_sf = R @ (self.sf*x_obs) + np.tile(np.array([self.center_position]).T,(1,numPoints))
        else:
            x_obs_sf = R @ (x_obs*np.tile(self.sf,(1,numPoints))) + np.tile(self.center_position, (numPoints,1)).T 

        x_obs = R @ x_obs + np.tile(np.array([self.center_position]).T,(1,numPoints))
        
        if sum(a_temp) == 0:
            self.x_obs = x_obs.T.tolist()
            self.x_obs_sf = x_obs_sf.T.tolist()
        else:
             return x_obs_sf
         
    def compute_R(self):
        # Compute the rotation matrix in 2D and 3D
        if self.orientation == 0:
            self.rotMatrix = np.eye(self.dim)
            return
        
        # rotating the query point into the obstacle frame of reference
        if self.dim==2:
            self.rotMatrix = np.array([[cos(self.orientation), -sin(self.orientation)],
                                       [sin(self.orientation),  cos(self.orientation)]])
        elif self.dim==3:
            R_x = np.array([[1, 0, 0,],
                        [0, np.cos(self.orientation[0]), np.sin(self.orientation[0])],
                        [0, -np.sin(self.orientation[0]), np.cos(self.orientation[0])] ])

            R_y = np.array([[np.cos(self.orientation[1]), 0, -np.sin(self.orientation[1])],
                        [0, 1, 0],
                        [np.sin(self.orientation[1]), 0, np.cos(self.orientation[1])] ])

            R_z = np.array([[np.cos(self.orientation[2]), np.sin(self.orientation[2]), 0],
                        [-np.sin(self.orientation[2]), np.cos(self.orientation[2]), 0],
                        [ 0, 0, 1] ])

            self.rotMatrix= R_x.dot(R_y).dot(R_z)
        else:
            warnings.warn('rotation not yet defined in dimensions d > 3 !')
            self.rotMatrix = np.eye(self.dim)
    
    def obs_check_collision(self, ):
        print('TODO: check class')
        


class Ellipse(Obstacle):
    pass


class Cuboid(Obstacle):
    def __init__(self,  orientation=0, sf=1, absolut_margin=0, xd=[0,0], sigma=1,  w=0, x_start=0, x_end=0, timeVariant=False, axes_length=[1,1], a=None, center_position=[0,0],  tail_effect=True, always_moving=True, is_boundary=False, *args, **kwargs):
        # This class defines obstacles to modulate the DS around it
        # At current stage the function focuses on Ellipsoids, but can be extended to more general obstacles
    # def __init_pose__():
    # def __init_obstacle(*args, **kwargs):
        
        # Leave at the moment for backwards compatibility
        self.axes_length = np.array(axes_length)

        # self.margin_axes =  self.axes_length*np.array(sf)+np.array(delta_margin)
        
        # self.sigma = sigma
        self.tail_effect = tail_effect # Modulation if moving away behind obstacle

        # Obstacle attitude
        self.center_position = np.array(center_position) # new name for future version
        self.center_position = center_position # new name for future version
        
        self.orientation = orientation
        self.th_r = orientation

        self.dim = len(center_position) #Dimension of space

        # TODO: REMOVE THEESE
        self.sigma = sigma
        self.sf = sf

        self.absolut_margin = absolut_margin
        
        self.rotMatrix = []
        self.compute_R() # Compute Rotation Matrix
        
        self.resolution = 0 #Resolution of drawing

        self.edge_points = np.zeros((self.dim, 4))
        self.edge_points[:,0] = self.axes_length/2.0*np.array([1,1])
        self.edge_points[:,1] = self.axes_length/2.0*np.array([-1,1])
        self.edge_points[:,2] = self.axes_length/2.0*np.array([-1,-1])
        self.edge_points[:,3] = self.axes_length/2.0*np.array([1,-1])
        
        self.hull_edge = np.copy(self.edge_points) # TODO: what if point outside?

        self.normal_vector = np.zeros(self.edge_points.shape)
        self.normalDistance2center = np.zeros(self.edge_points.shape[1])
        
        for ii in range(self.normal_vector.shape[1]):
            self.normal_vector[:, ii] = (self.edge_points[:,(ii+1)%self.normal_vector.shape[1]]
                                         - self.edge_points[:,ii])
            if self.dim==2:
                self.normal_vector[:, ii] = np.array([self.normal_vector[1, ii],
                                                      -self.normal_vector[0, ii],])
            else:
                warnings.warn("Implement for d>2.")
        
            self.normalDistance2center[ii] = self.normal_vector[:, ii].T @ self.edge_points[:, ii]

            if self.normalDistance2center[ii] < 0:
                self.normal_vector[:, ii] = (-1) * self.normal_vector[:, ii]
                self.normalDistance2center[ii] = (-1)*self.normalDistance2center[ii]
                
        # Normalize
        self.normal_vector /= np.tile(LA.norm(self.normal_vector, axis=0), (self.dim,1))
        
        # TODO add margin & rename
        # self.x_obs = np.zeros((self.edge_points.shape)).T
        # for ii in range(self.edge_points.shape[1]):
            # self.x_obs[ii, :] = self.rotMatrix @ self.edge_points[:,0] + self.obs
        # self.x_obs_sf = self.edge_points.T

        self.timeVariant = timeVariant
        if self.timeVariant:
            self.func_xd = 0
            self.func_w = 0
            
        else:
            self.always_moving = always_moving
        
        if sum(np.abs(xd)) or w or self.timeVariant:
            # Dynamic simulation - assign varibales:
            self.x_start = x_start
            self.x_end = x_end
            self.always_moving = False
        else:
            self.x_start = 0
            self.x_end = 0
            
        self.w = w # Rotational velocity
        self.xd = xd #

        # Reference point // Dyanmic center
        self.reference_point = np.zeros(self.dim) # At center

        self.reference_point_is_inside = True

        self.is_boundary = is_boundary

    # def draw_obstacle(self, draw_obstacleMargin=True, n_points=4):
        # for ii

        
    def draw_obstacle(self, include_margin=False, n_curve_points=5, numPoints=None):
        num_edges = self.edge_points.shape[1]
        
        if not type(numPoints)==None:
            n_curve_points = int(np.ceil(numPoints/(num_edges+1)) )
            # warnings.warn("Remove numPoints from function argument.")
        
        self.bounday_points = np.zeros((self.dim, num_edges+1))
        
        for ii in range(2):
            for jj in range(2):
                self.bounday_points[:, ii+jj*2] = self.edge_points[:,ii+jj*2]
                self.bounday_points[:,ii+jj*2] = self.rotMatrix @ self.bounday_points[:,ii+jj*2] + np.array([self.center_position])
        
        self.bounday_points[:, -1]  = self.bounday_points[:, 0]

        angles = np.linspace(0, 2*pi, num_edges*n_curve_points+1)
        
        obs_margin_cirlce = self.absolut_margin* np.vstack((np.cos(angles),
                                                            np.sin(angles)))

        x_obs_sf = np.zeros((self.dim, 0))
        for ii in range(num_edges):
            x_obs_sf = np.hstack((x_obs_sf, np.tile(self.edge_points[:, ii], (n_curve_points+1, 1) ).T + obs_margin_cirlce[:, ii*n_curve_points:(ii+1)*n_curve_points+1] ))
        x_obs_sf  = np.hstack((x_obs_sf, x_obs_sf[:,0].reshape(2,1)))

        for jj in range(x_obs_sf.shape[1]): # TODO replace for loop with numpy-math
            x_obs_sf[:, jj] = self.rotMatrix @ x_obs_sf[:, jj] + np.array([self.center_position])

        # TODO rename more intuitively
        self.x_obs = self.bounday_points.T # Surface points
        self.x_obs_sf = x_obs_sf.T # Margin points
        
    
    def get_gamma(self, position, in_global_frame=False, norm_order=2):
        if not type(position)==np.ndarray:
            position = np.array(position)

        # Rename
        if in_global_frame:
            position = self.transform_global2relative(position)

        

        # TODO extend rule to include points with Gamma < 1 for both cases
        if self.is_boundary:
            dist2hull = np.ones(self.edge_points.shape[1])*(-1)

            mag_position = LA.norm(position)
            if mag_position==0: # aligned with center, treat sepearately
                return  # 
                
            reference_dir = position / mag_position
            
            for ii in range(self.edge_points.shape[1]):
                surface_dir = (self.edge_points[:, (ii+1)%self.edge_points.shape[1]]
                               - self.edge_points[:, ii])

                # vec_tan*a + edge_point = r*b + 0
                # [position vec_tan] [b -a] = edge_point
                
                dist2hull[ii] = LA.lstsq(np.vstack((reference_dir, surface_dir)).T, self.edge_points[:, ii], rcond=None)[0][0]

            Gamma = np.min(dist2hull[dist2hull>0])/mag_position
            
        else:
            distances2plane = self.get_distance_to_hullEdge(position)
            
            delta_Gamma = np.min(distances2plane) - self.absolut_margin
            ind_outside = (distances2plane > 0)
            delta_Gamma = (LA.norm(distances2plane[ind_outside], ord=norm_order)-self.absolut_margin)
            Gamma = 1 + delta_Gamma / np.max(self.axes_length)
            

        return Gamma
        
        # for ii in np.arange(self.edge_points.shape[1]):
        #     reference_line = {"point_start":[0,0],
        #                       "point_end":position}

        #     if ii+1<self.edge_points.shape[1]:
        #         ii_end = ii
        #     else:
        #         ii_end = 0
                
        #     tangent_line = {"point_start":self.edge_points[:,ii],
        #                     "point_end":self.edge_points[:,(ii+1)%self.edge_points.shape[1]]}
            
        #     ind_intersect, dist_intersect = self.are_lines_intersecting(reference_line, tangent_line)
        #     if ind_intersect:
        #         return (LA.norm(position))/dist_intersect

        # warnings.warn("NO INTERSECTION OF CUBOID.")
        # return 1


    def get_normal_direction(self, position, in_global_frame=False, normalize=True):
        if in_global_frame:
            position = self.transform_global2relative(position)
            
        ind_intersect = np.zeros(self.normalDistance2center.shape, dtype=bool)

        distances2plane = self.get_distance_to_hullEdge(position)
        # if np.sum(ind_outside)>0:
        # tangent_line = np.zeros(self.normal_vector.shape)
        # position_line = np.zeros(self.normal_vector.shape)
        ind_outside = (distances2plane > 0)

        if self.is_boundary and np.sum(ind_outside)==0:
            dist2hull = np.ones(self.edge_points.shape[1])*(-1)

            mag_position = LA.norm(position)
            if mag_position==0: # aligned with center, treat sepearately
                return np.hstack((1, np.zeros(self.dim-1)))
                # return None
                
            reference_dir = position / mag_position
            
            for ii in range(self.edge_points.shape[1]):
                # TODO - try to optimze
                surface_dir = (self.edge_points[:, (ii+1)%self.edge_points.shape[1]]
                               - self.edge_points[:, ii]) 

                # vec_tan*a + edge_point = r*b + 0
                # [position vec_tan] [b -a] = edge_point
                dist2hull[ii] = LA.lstsq(np.vstack((reference_dir, surface_dir)).T, self.edge_points[:, ii], rcond=None)[0][0]

            weights = self.get_distance_weight(dist2hull-mag_position)
            
        else:
            if not np.sum(ind_outside): # zero value
                # TODO solver better
                return np.ones(self.dim)/self.dim # Nonsingular value

            angle2hull = np.zeros(ind_outside.shape)
            for ii in range(self.edge_points.shape[1]):
                if distances2plane[ii] <= 0 or not ind_outside[ii]:
                    angle2hull[ii] = pi
                    continue

                # TODO - don't use reference point, but little 'offset' to avoid singularity
                # Get closest point
                edge_points_temp = np.vstack((self.edge_points[:,ii],
                                         self.edge_points[:,(ii+1)%self.edge_points.shape[1]])).T
                ind_sort = np.argsort(LA.norm(np.tile(position,(2,1)).T-edge_points_temp, axis=0))

                # tangent_line[:,ii] = edge_points_temp[ind_sort[1]] - edge_points_temp[ind_sort[0]]
                # position_line[:,ii] = position - edge_points_temp[ind_sort[0]]

                tangent_line = edge_points_temp[:,ind_sort[1]] - edge_points_temp[:, ind_sort[0]]
                position_line = position - edge_points_temp[:, ind_sort[0]]

                angle2hull[ii] = self.get_angle2dir(position_line, tangent_line)

            if not np.sum(ind_intersect): # nonzero
                # warnings.warn("No intersection found.")
                normal_vector = np.ones(self.dim)
            
            weights = self.get_angle_weight(angle2hull)

        normal_vector = get_directional_weighted_sum(reference_direction=position, directions=self.normal_vector, weights=weights, normalize=False, obs=self, position=position, normalize_reference=True)
        if normalize:
            normal_vector = normal_vector/LA.norm(normal_vector)
        
        if False:
            # self.draw_reference_hull(normal_vector, position)
            pos_abs = self.transform_relative2global(position)
            norm_abs = self.transform_relative2global_dir(normal_vector)
            plt.quiver(pos_abs[0], pos_abs[1], norm_abs[0], norm_abs[1], color='g')
            ref_abs = self.get_reference_direction(position)
            ref_abs = self.transform_relative2global_dir(ref_abs)
            plt.quiver(pos_abs[0], pos_abs[1], ref_abs[0], ref_abs[1], color='k')

            plt.ion()
            plt.show()
            
            
        return normal_vector
