#define _GNU_SOURCE
#include <Python.h>
#include <sys/syscall.h>
#include <sys/mount.h>
#include <sched.h>
#include <sys/wait.h>
#include <unistd.h>

#define STACK_SIZE 32768

static PyObject *
pivot_root(PyObject *self, PyObject *args) {
	const char *put_old, *new_root;

	if (!PyArg_ParseTuple(args, "ss", &new_root, &put_old))
		return NULL;

	if (syscall(SYS_pivot_root, new_root, put_old) == -1) {
		PyErr_SetFromErrno(PyExc_RuntimeError);
		return NULL;
	} else {
		Py_RETURN_NONE;
	}
}

static PyObject *
_mount(PyObject *self, PyObject *args) {
	const char *source, *target, *filesystemtype, *mountopts;
	unsigned long mountflags;

	if (!PyArg_ParseTuple(args, "zszkz", &source, &target, &filesystemtype, &mountflags, &mountopts)) {
		return NULL;
	}

	if (mount(source, target, filesystemtype, mountflags, mountopts) == -1) {
		PyErr_SetFromErrno(PyExc_RuntimeError);
		return NULL;
	} else {
		Py_RETURN_NONE;
	}
}

static PyObject *
_umount(PyObject *self, PyObject *args) {
	const char *target;

	if (!PyArg_ParseTuple(args, "s", &target)) {
		return NULL;
	}

	if (umount(target) == -1) {
		PyErr_SetFromErrno(PyExc_RuntimeError);
		return NULL;
	} else {
		Py_RETURN_NONE;
	}
}

static PyObject *
_umount2(PyObject *self, PyObject *args) {
	const char *target;
	int flags;

	if (!PyArg_ParseTuple(args, "si", &target, &flags)) {
		return NULL;
	}

	if (umount2(target, flags) == -1) {
		PyErr_SetFromErrno(PyExc_RuntimeError);
		return NULL;
	} else {
		Py_RETURN_NONE;
	}
}

static PyObject *
_unshare(PyObject *self, PyObject *args) {
	int clone_flags;

	if (!PyArg_ParseTuple(args, "i", &clone_flags))
		return NULL;

	if (unshare(clone_flags) == -1) {
		PyErr_SetFromErrno(PyExc_RuntimeError);
		return NULL;
	} else {
		Py_RETURN_NONE;
	}
}

static PyObject *
_setns(PyObject *self, PyObject *args) {
	int fd, nstype;

	if (!PyArg_ParseTuple(args, "ii", &fd, &nstype))
		return NULL;

	if (setns(fd, nstype) == -1) {
		PyErr_SetFromErrno(PyExc_RuntimeError);
		return NULL;
	} else {
		Py_RETURN_NONE;
	}
}

struct py_clone_args {
	PyObject *callback;
	PyObject *callback_args;
};

static PyObject *
_sethostname(PyObject *self, PyObject *args) {
	const char *hostname;

	if (!PyArg_ParseTuple(args, "s", &hostname))
		return NULL;

	if (sethostname(hostname, strlen(hostname)) == -1) {
		PyErr_SetFromErrno(PyExc_RuntimeError);
		return NULL;
	}

	Py_RETURN_NONE;
}

static PyMethodDef LinuxMethods[] = {
    {"pivot_root",  pivot_root,   METH_VARARGS, "pivot_root(new_root, put_old)"},
    {"unshare",     _unshare,     METH_VARARGS, "unshare(flags)"},
    {"setns",       _setns,       METH_VARARGS, "setns(fd, nstype)"},
    {"sethostname", _sethostname, METH_VARARGS, "sethostname(hostname)"},
    {"mount",       _mount,       METH_VARARGS, "mount(src, tgt, fs, flags, opts)"},
    {"umount",      _umount,      METH_VARARGS, "umount(target)"},
    {"umount2",     _umount2,     METH_VARARGS, "umount2(target, flags)"},
    {NULL, NULL, 0, NULL}
};

static struct PyModuleDef linuxmodule = {
	PyModuleDef_HEAD_INIT,
	"linux",
	NULL,
	-1,
	LinuxMethods
};

PyMODINIT_FUNC
PyInit_linux(void)
{
	PyObject *module = PyModule_Create(&linuxmodule);


	// clone constants
	PyModule_AddIntConstant(module, "CLONE_NEWNS", CLONE_NEWNS);     // mount namespace
	PyModule_AddIntConstant(module, "CLONE_NEWUTS", CLONE_NEWUTS);   // UTS (hostname) namespace
	PyModule_AddIntConstant(module, "CLONE_NEWPID", CLONE_NEWPID);   // PID namespace
	PyModule_AddIntConstant(module, "CLONE_NEWUSER", CLONE_NEWUSER); // users namespace
	PyModule_AddIntConstant(module, "CLONE_NEWIPC", CLONE_NEWIPC);   // IPC namespace
	PyModule_AddIntConstant(module, "CLONE_NEWNET", CLONE_NEWNET);   // network namespace
	PyModule_AddIntConstant(module, "CLONE_THREAD", CLONE_THREAD);

	// mount constants
	PyModule_AddIntConstant(module, "MS_RDONLY", MS_RDONLY);               /* Mount read-only.  */
	PyModule_AddIntConstant(module, "MS_NOSUID", MS_NOSUID);               /* Ignore suid and sgid bits.  */
	PyModule_AddIntConstant(module, "MS_NODEV", MS_NODEV);                 /* Disallow access to device special files.  */
	PyModule_AddIntConstant(module, "MS_NOEXEC", MS_NOEXEC);               /* Disallow program execution.  */
	PyModule_AddIntConstant(module, "MS_SYNCHRONOUS", MS_SYNCHRONOUS);     /* Writes are synced at once.  */
	PyModule_AddIntConstant(module, "MS_REMOUNT", MS_REMOUNT);             /* Alter flags of a mounted FS.  */
	PyModule_AddIntConstant(module, "MS_MANDLOCK", MS_MANDLOCK);           /* Allow mandatory locks on an FS.  */
	PyModule_AddIntConstant(module, "MS_DIRSYNC", MS_DIRSYNC);             /* Directory modifications are synchronous.  */
	PyModule_AddIntConstant(module, "MS_NOATIME", MS_NOATIME);             /* Do not update access times.  */
	PyModule_AddIntConstant(module, "MS_NODIRATIME", MS_NODIRATIME);       /* Do not update directory access times.  */
	PyModule_AddIntConstant(module, "MS_BIND", MS_BIND);                   /* Bind directory at different place.  */
	PyModule_AddIntConstant(module, "MS_MOVE", MS_MOVE);
	PyModule_AddIntConstant(module, "MS_REC", MS_REC);                     /* Recursive loopback */
	PyModule_AddIntConstant(module, "MS_SILENT", MS_SILENT);
	PyModule_AddIntConstant(module, "MS_POSIXACL", MS_POSIXACL);           /* VFS does not apply the umask.  */
	PyModule_AddIntConstant(module, "MS_UNBINDABLE", MS_UNBINDABLE);       /* Change to unbindable.  */
	PyModule_AddIntConstant(module, "MS_PRIVATE", MS_PRIVATE);             /* Change to private.  */
	PyModule_AddIntConstant(module, "MS_SLAVE", MS_SLAVE);                 /* Change to slave.  */
	PyModule_AddIntConstant(module, "MS_SHARED", MS_SHARED);               /* Change to shared.  */
	PyModule_AddIntConstant(module, "MS_RELATIME", MS_RELATIME);           /* Update atime relative to mtime/ctime.  */
	PyModule_AddIntConstant(module, "MS_KERNMOUNT", MS_KERNMOUNT);         /* This is a kern_mount call.  */
	PyModule_AddIntConstant(module, "MS_I_VERSION", MS_I_VERSION);         /* Update inode I_version field.  */
	PyModule_AddIntConstant(module, "MS_STRICTATIME", MS_STRICTATIME);     /* Always perform atime updates.  */
	PyModule_AddIntConstant(module, "MS_ACTIVE", MS_ACTIVE);
	PyModule_AddIntConstant(module, "MS_NOUSER", MS_NOUSER);
	PyModule_AddIntConstant(module, "MNT_DETACH", MNT_DETACH);             /* Just detach from the tree.  */
	PyModule_AddIntConstant(module, "MS_MGC_VAL", MS_MGC_VAL);
	
	return module;
}