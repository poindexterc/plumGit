from django.db import models

class Folders(models.Model):
    folderName = models.CharField(max_length = 30)
    folderID = models.IntegerField()
    folderLastModifiedWhen = models.DateTimeField()
    folderLastModifiedWho = models.IntegerField()

    # Project ID
    projectID = models.IntegerField()

    def __unicode__(self):
        return self.folderName

    def __str__(self):
        return self.folderName

class Project(models.Model):
    projectName = models.CharField(max_length = 30)
    projectCollaborators = models.TextField()
    projectFolders = models.TextField()
    projectID = models.IntegerField()
    projectColor = models.TextField()
    projectLastModifiedWhen = models.DateTimeField()
    projectLastModifiedWho = models.IntegerField()

    def __unicode__(self):
        return self.projectName

    def __str__(self):
        return self.projectName

class Files(models.Model):
    fileName = models.CharField(max_length = 30)
    fileID = models.IntegerField()
    fileData = models.TextField()
    fileType = models.CharField(max_length = 10)
    fileHighlight = models.CharField(max_length = 20)
    fileCreationDateTime = models.DateTimeField(auto_now = True)
    fileLastModifiedWhen = models.DateTimeField()
    fileLastModifiedWho = models.IntegerField()
    # Project and Folder IDs
    projectID = models.IntegerField()
    folderID = models.IntegerField()

    def __unicode__(self):
        return self.fileName
    
    def __str__(self):
        return self.fileName

class User(models.Model):
    username = models.CharField(max_length = 20)
    userID = models.IntegerField()
    userProjects = models.TextField()
    password = models.CharField(max_length = 50)
    userAdminProjects = models.TextField()

    def __unicode__(self):
        return self.username

    def __str__(self):
        return self.username