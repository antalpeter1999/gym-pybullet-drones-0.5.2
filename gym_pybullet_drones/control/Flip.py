import math
import numpy as np


class Flip:
    """Functions for the flip maneuvre."""
    def __init__(self):
        self.mass = 0.028
        self.Ixx = 0.0000158
        #self.Ixx = 2.3951e-5
        self.inertiaMatrix = np.diag(np.array([0.0000158, 0.0000158, 0.00002926]))
        #self.inertiaMatrix = np.diag(np.array([2.3951e-5, 2.3951e-5, 3.2347e-5]))
        self.length = 0.046
        self.Bup = 20.86
        self.Bdown = 6.246
        self.Cpmax = 2 * np.pi * 1800/180
        self.gravity = 9.806
        self.thrustToDrag = 2.093e-6  #0.006
        self.KF = 3.16e-10
        self.PWM2RPM_SCALE = 0.2685
        self.PWM2RPM_CONST = 4070.3

    def get_acceleration(self, p0, p3):
        """Compute the acceleration from the generated parameters."""
        ap = {
            'acc': (-self.mass * self.length * (self.Bup - p0) / (4 * self.Ixx)),
            'start': (self.mass * self.length * (self.Bup - self.Bdown) / (4 * self.Ixx)),
            'coast': 0,
            'stop': (-self.mass * self.length * (self.Bup - self.Bdown) / (4 * self.Ixx)),
            'recover': (self.mass * self.length * (self.Bup - p3) / (4 * self.Ixx)),
        }
        return ap

    def get_initial_parameters(self):
        """Initial parameters."""
        p0 = p3 = 0.9 * self.Bup
        p1 = p4 = 0.1
        acc_start = self.get_acceleration(p0, p3)['start']
        p2 = (2 * np.pi / self.Cpmax) - (self.Cpmax / acc_start)
        return [p0, p1, p2, p3, p4]

    def get_sections(self, parameters):
        """Compute the 5 regions of the flight as defined in the paper."""
        sections = np.zeros(5, dtype='object')
        [p0, p1, p2, p3, p4] = parameters

        ap = self.get_acceleration(p0, p3)

        T2 = (self.Cpmax - p1 * ap['acc']) / ap['start']
        T4 = -(self.Cpmax + p4 * ap['recover']) / ap['stop']

        aq = 0
        ar = 0

        # 1. Accelerate
        sections[0] = (self.mass * p0, [ap['acc'], aq, ar], p1)

        temp = self.mass * self.Bup - 2 * abs(ap['start']) * self.Ixx / self.length
        sections[1] = (temp, [ap['start'], aq, ar], T2)

        sections[2] = (self.mass * self.Bdown, [ap['coast'], aq, ar], p2)

        temp = self.mass * self.Bup - 2 * abs(ap['stop']) * self.Ixx / self.length
        sections[3] = (temp, [ap['stop'], aq, ar], T4)

        sections[4] = (self.mass * p3, [ap['recover'], aq, ar], p4)
        return sections

    def motor_thrust(self, moments, coll_thrust):
        """Compute the individual motor thrusts

        Parameters
        ----------
        moments : numpy.array
            The moments along each of the axis [Mp, Mq, Mr]
        coll_thrust : float
            The collective thrust generated by all motors
        Returns
        -------
        numpy.array
            The thrust generated by each motor [T1, T2, T3, T4]
        """
        [mp, mq, mr] = moments
        thrust = np.zeros(4)
        temp1add = coll_thrust + mr / self.thrustToDrag
        temp1sub = coll_thrust - mr / self.thrustToDrag

        temp2p = 2 * mp / self.length
        temp2q = 2 * mq / self.length

        thrust[0] = temp1add - temp2q
        thrust[1] = temp1sub + temp2p
        thrust[2] = temp1add + temp2q
        thrust[3] = temp1sub - temp2p

        return thrust / 4.0

    def motor_pwm(self, moments, coll_thrust):
        """Compute the individual motor thrusts

        Parameters
        ----------
        moments : numpy.array
            The moments along each of the axis [Mp, Mq, Mr]
        coll_thrust : float
            The collective thrust generated by all motors
        Returns
        -------
        numpy.array
            The thrust generated by each motor [T1, T2, T3, T4]
        """
        [mp, mq, mr] = moments
        PWM = np.zeros(4)
        temp1add = coll_thrust + mr / self.thrustToDrag
        temp1sub = coll_thrust - mr / self.thrustToDrag

        temp2p = 2 * mp / self.length
        temp2q = 2 * mq / self.length

        PWM[0] = coll_thrust / (self.thrustToDrag * 4)
        PWM[1] = (coll_thrust + 2 * mp / self.length) / (self.thrustToDrag * 4)
        PWM[2] = coll_thrust / (self.thrustToDrag * 4)
        PWM[3] = (coll_thrust - 2 * mp / self.length) / (self.thrustToDrag * 4)

        for i in range(len(PWM)):
            if PWM[i] >= 65000:
                PWM[i] = 65000
            if PWM[i] <= 20500:
                PWM[i] = 20500
        return PWM

    def moments(self, desired_acc, angular_vel):
        """Compute the moments

        Parameters
        ----------
        desired_acc : numpy.array
            The desired angular acceleration that the system should achieve. This
            should be of form [dp/dt, dq/dt, dr/dt]
        angular_vel : numpy.array
            The current angular velocity of the system. This
            should be of form [p, q, r]

        Returns
        -------
        numpy.array
            The desired moments of the system
        """
        inverse_inertia = np.linalg.inv(self.inertiaMatrix)
        part1 = np.dot(inverse_inertia, angular_vel)
        part2 = np.dot(self.inertiaMatrix, angular_vel)
        cross = np.cross(part1, part2)
        value = desired_acc + cross
        return np.dot(self.inertiaMatrix, value)

    def compute_control_from_section(self, section, angular_vel):
        # tau = self.moments(section[1], angular_vel)
        tau = np.array([self.Ixx * section[1][0], 0, 0])
        thrusts = self.motor_thrust(tau, section[0])
        # motor_velo = np.sqrt(1./self.KF * thrusts)
        PWM = self.motor_pwm(tau, section[0])
        # print(PWM)
        return self.PWM2RPM_CONST + self.PWM2RPM_SCALE*PWM
